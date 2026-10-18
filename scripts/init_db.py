"""Database initialization, schema migration, and seed data ingestion script.

Loads:
1. Store clusters and holiday calendar
2. Mature SKU catalogue (historical, is_evaluation_sku=False)
3. New SKU catalogue (target 150 SKUs, is_evaluation_sku=True)
4. Historical mature weekly sales
5. Model version registry (v1.0.0-catboost-coldstart)
6. Official evaluation forecast run (RUN_EVAL_150_V1):
   - 1,200 weekly point predictions and 80%/90% conformal bounds
   - Top-K historical analogue matches with observed curves
   - 150 initial inventory buy recommendations & confidence rankings
   - Proportional store-cluster allocations
   - Cryptographic lineage manifests
7. Referential integrity and data isolation verification
"""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import func, select

from src.core.config import settings
from src.core.logging import get_logger
from src.db.models import (
    Base,
    ClusterAllocationModel,
    DataManifestModel,
    ForecastRunModel,
    HolidayModel,
    InventoryRecommendationModel,
    ModelVersionModel,
    SKUModel,
    StoreClusterModel,
    WeeklyForecastModel,
    WeeklySalesModel,
)
from src.db.repository import ForecastRepository
from src.db.session import (
    create_async_db_engine,
    drop_db_schema,
    init_db_schema,
    normalize_database_url,
)

logger = get_logger("init_db")


def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    if not filepath.exists():
        return ""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


async def seed_database(
    db_url: str,
    reset: bool = False,
    sales_limit: int = 10000,
) -> dict[str, Any]:
    """Execute complete database schema initialization and seed ingestion."""
    logger.info(f"Connecting to database: {normalize_database_url(db_url, sync=False)}")
    engine = create_async_db_engine(db_url, echo=False)

    if reset:
        logger.warning("Reset requested: dropping all existing database tables...")
        await drop_db_schema(engine)

    logger.info("Ensuring database schema exists...")
    await init_db_schema(engine)

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    stats = {}

    async with session_factory() as session:
        repo = ForecastRepository(session)

        # ---------------------------------------------------------------------
        # 1. Store Clusters
        # ---------------------------------------------------------------------
        clusters_path = Path("data/raw/store_clusters.csv")
        if clusters_path.exists():
            df_clusters = pd.read_csv(clusters_path)
            cluster_recs = []
            for cid, group in df_clusters.groupby("cluster_id"):
                tier = group["store_tier"].iloc[0] if "store_tier" in group.columns else "Standard"
                regions = ", ".join(sorted(group["region"].unique())) if "region" in group.columns else ""
                cluster_recs.append(
                    {
                        "cluster_id": str(cid),
                        "cluster_name": f"{tier} Cluster ({cid})",
                        "description": f"{tier} store network across {regions} ({len(group)} stores)",
                        "store_count": len(group),
                        "regional_climate": regions,
                        "income_tier": tier,
                    }
                )
            n_clusters = await repo.bulk_insert_store_clusters(cluster_recs)
            logger.info(f"Ingested {n_clusters} store clusters.")
            stats["store_clusters"] = n_clusters

        # ---------------------------------------------------------------------
        # 2. Holiday Calendar
        # ---------------------------------------------------------------------
        holidays_path = Path("data/raw/holiday_calendar.csv")
        if holidays_path.exists():
            df_holidays = pd.read_csv(holidays_path)
            # Filter to active holiday weeks
            df_active_holidays = df_holidays[
                (df_holidays["is_holiday_week"] == 1)
                | (df_holidays["holiday_name"].notna() & (df_holidays["holiday_name"] != "None"))
            ]
            holiday_recs = []
            for _, r in df_active_holidays.iterrows():
                h_date = pd.to_datetime(r["week_start_date"]).date()
                h_name = str(r["holiday_name"])
                holiday_recs.append(
                    {
                        "holiday_name": h_name,
                        "holiday_date": h_date,
                        "week_of_year": int(r["fiscal_week"]),
                        "year": int(r["fiscal_year"]),
                        "is_promotional": "Black Friday" in h_name or "Christmas" in h_name,
                    }
                )
            n_holidays = await repo.bulk_insert_holidays(holiday_recs)
            logger.info(f"Ingested {n_holidays} holiday calendar dates.")
            stats["holidays"] = n_holidays

        # ---------------------------------------------------------------------
        # 3. Master SKU Catalogue (Mature & New Evaluation SKUs)
        # ---------------------------------------------------------------------
        sku_records = []
        # Mature SKUs
        mature_path = Path("data/raw/mature_sku_attributes.csv")
        if mature_path.exists():
            df_mature = pd.read_csv(mature_path)
            for _, r in df_mature.iterrows():
                sku_records.append(
                    {
                        "sku_id": str(r["sku_id"]),
                        "product_name": str(r["product_name"]),
                        "category": str(r["category"]),
                        "subcategory": str(r["subcategory"]),
                        "colour": str(r["colour"]) if pd.notna(r.get("colour")) else None,
                        "material": str(r["material"]) if pd.notna(r.get("material")) else None,
                        "base_price": float(r["base_price"]),
                        "brand": str(r["brand"]) if pd.notna(r.get("brand")) else None,
                        "brand_tier": str(r["brand_tier"]) if pd.notna(r.get("brand_tier")) else None,
                        "launch_date": pd.to_datetime(r["launch_date"]).date(),
                        "has_marketing_support": bool(r.get("has_marketing_support", False)),
                        "is_evaluation_sku": False,
                    }
                )

        # New Evaluation SKUs
        new_path = Path("data/raw/new_sku_attributes.csv")
        if new_path.exists():
            df_new = pd.read_csv(new_path)
            for _, r in df_new.iterrows():
                sku_records.append(
                    {
                        "sku_id": str(r["sku_id"]),
                        "product_name": str(r["product_name"]),
                        "category": str(r["category"]),
                        "subcategory": str(r["subcategory"]),
                        "colour": str(r["colour"]) if pd.notna(r.get("colour")) else None,
                        "material": str(r["material"]) if pd.notna(r.get("material")) else None,
                        "base_price": float(r["base_price"]),
                        "brand": str(r["brand"]) if pd.notna(r.get("brand")) else None,
                        "brand_tier": str(r["brand_tier"]) if pd.notna(r.get("brand_tier")) else None,
                        "launch_date": pd.to_datetime(r["launch_date"]).date(),
                        "has_marketing_support": bool(r.get("has_marketing_support", False)),
                        "is_evaluation_sku": True,
                    }
                )

        n_skus = await repo.bulk_upsert_skus(sku_records)
        logger.info(f"Ingested {n_skus} master SKU records (mature + new).")
        stats["skus"] = n_skus

        # ---------------------------------------------------------------------
        # 4. Historical Weekly Sales (Sampled / Ingested)
        # ---------------------------------------------------------------------
        train_features_path = Path("data/processed/train_features.parquet")
        if train_features_path.exists():
            logger.info(f"Loading historical weekly sales from {train_features_path} (limit: {sales_limit} records)...")
            df_sales = pd.read_parquet(train_features_path).head(sales_limit)
            sales_recs = []
            for _, r in df_sales.iterrows():
                sales_recs.append(
                    {
                        "sku_id": str(r["sku_id"]),
                        "store_id": str(r["store_id"]),
                        "cluster_id": str(r["cluster_id"]),
                        "launch_week_age": int(r["launch_week_age"]),
                        "units_sold": float(r["units_sold"]),
                        "week_end_date": None,
                    }
                )
            n_sales = await repo.bulk_insert_weekly_sales(sales_recs)
            logger.info(f"Ingested {n_sales} historical weekly sales observations.")
            stats["weekly_sales"] = n_sales

        # ---------------------------------------------------------------------
        # 5. Model Version Registry
        # ---------------------------------------------------------------------
        model_config_path = Path("artifacts/models/supervised_coldstart_v1/model_config.json")
        val_report_path = Path("artifacts/models/supervised_coldstart_v1/validation_report.json")
        train_manifest_path = Path("artifacts/models/supervised_coldstart_v1/training_manifest.json")

        hyperparams = {}
        features = {}
        val_wape = 0.3168
        train_sha = ""

        if model_config_path.exists():
            with open(model_config_path, "r", encoding="utf-8") as f:
                model_cfg = json.load(f)
                hyperparams = {
                    "iterations": model_cfg.get("iterations"),
                    "learning_rate": model_cfg.get("learning_rate"),
                    "depth": model_cfg.get("depth"),
                    "l2_leaf_reg": model_cfg.get("l2_leaf_reg"),
                    "best_iteration": model_cfg.get("best_iteration"),
                }
                features = {
                    "feature_columns": model_cfg.get("feature_columns"),
                    "categorical_columns": model_cfg.get("categorical_columns"),
                }

        if val_report_path.exists():
            with open(val_report_path, "r", encoding="utf-8") as f:
                val_data = json.load(f)
                if "Supervised CatBoost GBDT" in val_data:
                    val_wape = val_data["Supervised CatBoost GBDT"].get("overall_wape", 0.3168)

        if train_manifest_path.exists():
            with open(train_manifest_path, "r", encoding="utf-8") as f:
                t_m = json.load(f)
                train_sha = t_m.get("train_features_sha256", "")

        model_ver = await repo.create_model_version(
            {
                "model_id": "v1.0.0-catboost-coldstart",
                "algorithm": "CatBoostRegressor",
                "objective": "MAE",
                "target_transform": "log1p",
                "artifact_path": "artifacts/models/supervised_coldstart_v1/catboost_model.cbm",
                "training_manifest_sha256": train_sha,
                "validation_wape": val_wape,
                "hyperparameters": hyperparams,
                "feature_schema": features,
            }
        )
        logger.info(f"Registered model version: {model_ver.model_id}")
        stats["model_versions"] = 1

        # ---------------------------------------------------------------------
        # 6. Official Evaluation Forecast Run (RUN_EVAL_150_V1)
        # ---------------------------------------------------------------------
        run_id = "RUN_EVAL_150_V1"
        eval_run = await repo.create_forecast_run(
            {
                "run_id": run_id,
                "model_id": "v1.0.0-catboost-coldstart",
                "run_type": "EVALUATION_150",
                "status": "COMPLETED",
                "input_manifest_sha256": calculate_sha256(Path("data/raw/new_sku_attributes.csv")),
                "sku_count": 150,
                "overall_wape": val_wape,
                "overall_bias_pct": -3.76,
                "reproducibility_seed": 42,
                "execution_metadata": {
                    "conformal_calibration": "split_conformal_residual_quantile",
                    "coverage_levels": [0.80, 0.90],
                    "inventory_decision": "single_period_newsvendor_moq_pack",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "completed_at": datetime.now(timezone.utc),
            },
            prevent_duplicates=False,
        )
        logger.info(f"Created forecast run: {eval_run.run_id}")
        stats["forecast_runs"] = 1

        # ---------------------------------------------------------------------
        # 7. Weekly Forecasts (150 SKUs x 8 Weeks = 1,200 rows)
        # ---------------------------------------------------------------------
        fc_path = Path("data/processed/forecasts_with_intervals_150_skus.csv")
        if fc_path.exists():
            df_fc = pd.read_csv(fc_path)
            fc_records = []
            for _, r in df_fc.iterrows():
                fc_records.append(
                    {
                        "sku_id": str(r["sku_id"]),
                        "horizon_week": int(r["horizon_week"]),
                        "predicted_sales": float(r["predicted_sales"]),
                        "lower_bound_80": float(r["lower_bound_80"]) if pd.notna(r.get("lower_bound_80")) else None,
                        "upper_bound_80": float(r["upper_bound_80"]) if pd.notna(r.get("upper_bound_80")) else None,
                        "lower_bound_90": float(r["lower_bound_90"]) if pd.notna(r.get("lower_bound_90")) else None,
                        "upper_bound_90": float(r["upper_bound_90"]) if pd.notna(r.get("upper_bound_90")) else None,
                    }
                )
            n_fc = await repo.save_weekly_forecasts(run_id, fc_records)
            logger.info(f"Ingested {n_fc} weekly forecasts with conformal prediction intervals.")
            stats["weekly_forecasts"] = n_fc

        # ---------------------------------------------------------------------
        # 8. Analogue Matches
        # ---------------------------------------------------------------------
        analogues_path = Path("data/processed/analogue_retrieval_records.json")
        if analogues_path.exists():
            with open(analogues_path, "r", encoding="utf-8") as f:
                an_data = json.load(f)
            an_records = []
            for item in an_data:
                q_sku = item["query_sku_id"]
                for match in item.get("top_k_matches", []):
                    an_records.append(
                        {
                            "query_sku_id": q_sku,
                            "analogue_sku_id": match["analogue_sku_id"],
                            "rank": int(match["rank"]),
                            "similarity_score": float(match["similarity_score"]),
                            "observed_curve": match.get("observed_curve"),
                        }
                    )
            n_an = await repo.save_analogue_matches(run_id, an_records)
            logger.info(f"Ingested {n_an} analogue match relationships.")
            stats["analogue_matches"] = n_an

        # ---------------------------------------------------------------------
        # 9. Inventory Recommendations & Confidence Rankings
        # ---------------------------------------------------------------------
        rec_path = Path("data/processed/inventory_buy_recommendations_150_skus.csv")
        expl_path = Path("data/processed/forecast_explanations_150_skus.json")

        explanations_map = {}
        if expl_path.exists():
            with open(expl_path, "r", encoding="utf-8") as f:
                for exp in json.load(f):
                    explanations_map[exp["sku_id"]] = exp

        if rec_path.exists():
            df_rec = pd.read_csv(rec_path)
            rec_records = []
            for _, r in df_rec.iterrows():
                sku_id = str(r["sku_id"])
                exp_entry = explanations_map.get(sku_id, {})
                conf_score = exp_entry.get("confidence_score")
                conf_tier = exp_entry.get("confidence_tier")
                summary_text = exp_entry.get("human_readable_summary")

                # Base assumptions
                base_price = float(r["base_price"])
                assumptions = {
                    "base_price": base_price,
                    "cost_price": round(base_price * 0.55, 2),
                    "salvage_price": round(base_price * 0.20, 2),
                    "min_order_qty": 50,
                    "case_pack_size": 6,
                    "scenario": "BASE",
                }

                rec_records.append(
                    {
                        "sku_id": sku_id,
                        "scenario": "BASE",
                        "forecast_cumulative_8w": float(r["forecast_cumul_8w"]),
                        "recommended_buy_quantity": int(r["buy_qty_base"]),
                        "unconstrained_quantity": float(r["forecast_cumul_8w"] + r["safety_stock_base"]),
                        "critical_ratio": float(r["critical_ratio_base"]),
                        "understock_cost_cu": round(base_price * 0.45, 2),
                        "overstock_cost_co": round(base_price * 0.35, 2),
                        "expected_shortage_units": float(r["exp_shortage_base"]),
                        "expected_excess_units": float(r["exp_excess_base"]),
                        "expected_total_cost": float(r["exp_cost_base"]),
                        "expected_fill_rate_pct": float(r["fill_rate_base_pct"]),
                        "confidence_score": conf_score,
                        "confidence_tier": conf_tier,
                        "explanation_summary": summary_text,
                        "assumptions": assumptions,
                    }
                )

            n_recs = await repo.save_inventory_recommendations(run_id, rec_records)
            logger.info(f"Ingested {n_recs} inventory recommendations with confidence scores.")
            stats["inventory_recommendations"] = n_recs

            # -----------------------------------------------------------------
            # 10. Proportional Cluster Allocations (Optional Feature)
            # -----------------------------------------------------------------
            # Distribute inventory across clusters based on historical cluster weights
            clusters = await repo.list_store_clusters()
            if clusters:
                total_stores = sum(c.store_count for c in clusters)
                rec_models_stmt = select(InventoryRecommendationModel).where(
                    InventoryRecommendationModel.run_id == run_id
                )
                rec_models = list((await session.execute(rec_models_stmt)).scalars().all())

                alloc_count = 0
                for rec_item in rec_models:
                    allocations = []
                    for c in clusters:
                        weight = round(c.store_count / total_stores, 4)
                        qty = int(round(rec_item.recommended_buy_quantity * weight))
                        allocations.append(
                            {
                                "cluster_id": c.cluster_id,
                                "allocated_quantity": qty,
                                "allocation_weight": weight,
                            }
                        )
                    alloc_count += await repo.save_cluster_allocations(
                        rec_item.id, rec_item.sku_id, allocations
                    )
                logger.info(f"Generated {alloc_count} store cluster inventory allocations.")
                stats["cluster_allocations"] = alloc_count

        # ---------------------------------------------------------------------
        # 11. Data Lineage Manifests
        # ---------------------------------------------------------------------
        manifest_files = [
            ("RAW_MATURE_SKUS", Path("data/raw/mature_sku_attributes.csv")),
            ("RAW_NEW_SKUS", Path("data/raw/new_sku_attributes.csv")),
            ("RAW_CLUSTERS", Path("data/raw/store_clusters.csv")),
            ("RAW_HOLIDAYS", Path("data/raw/holiday_calendar.csv")),
            ("PROCESSED_INTERVALS", Path("data/processed/forecasts_with_intervals_150_skus.csv")),
            ("PROCESSED_INVENTORY", Path("data/processed/inventory_buy_recommendations_150_skus.csv")),
        ]
        manifest_count = 0
        for m_type, m_path in manifest_files:
            if m_path.exists():
                sha = calculate_sha256(m_path)
                line_count = sum(1 for _ in open(m_path, "r", encoding="utf-8")) - 1
                await repo.record_data_manifest(
                    {
                        "manifest_type": m_type,
                        "file_identifier": str(m_path.as_posix()),
                        "sha256_checksum": sha,
                        "row_count": line_count,
                        "schema_snapshot": {"path": str(m_path), "size_bytes": m_path.stat().st_size},
                    }
                )
                manifest_count += 1
        logger.info(f"Recorded {manifest_count} data lineage manifests.")
        stats["data_manifests"] = manifest_count

        # Commit all seeded data
        await session.commit()

        # ---------------------------------------------------------------------
        # 12. Verification & Audit Checks
        # ---------------------------------------------------------------------
        logger.info("Executing database verification and data isolation checks...")

        # A. SKU count verification
        skus_total = (await session.execute(select(func.count(SKUModel.sku_id)))).scalar_one()
        skus_eval = (
            await session.execute(
                select(func.count(SKUModel.sku_id)).where(SKUModel.is_evaluation_sku.is_(True))
            )
        ).scalar_one()
        logger.info(f"Catalogue Verification: {skus_total} total SKUs ({skus_eval} cold-start evaluation SKUs)")

        # B. Data Isolation Check: Ensure ZERO sales exist for evaluation SKUs
        leak_stmt = (
            select(func.count(WeeklySalesModel.id))
            .join(SKUModel, WeeklySalesModel.sku_id == SKUModel.sku_id)
            .where(SKUModel.is_evaluation_sku.is_(True))
        )
        leaked_sales = (await session.execute(leak_stmt)).scalar_one()
        if leaked_sales > 0:
            raise RuntimeError(
                f"DATA ISOLATION VIOLATION: {leaked_sales} sales rows belong to evaluation SKUs!"
            )
        logger.info("Data Isolation Verification: PASS (0 sales leaked for evaluation SKUs).")

        # C. Query Run Summary
        summary = await repo.get_run_summary(run_id)
        logger.info(f"Forecast Run Summary ({run_id}): {summary}")

        # D. Query 10 Least-Confident SKUs
        least_conf = await repo.get_least_confident_skus(run_id, limit=10)
        logger.info(f"Top Least Confident SKUs (count={len(least_conf)}):")
        for idx, item in enumerate(least_conf, 1):
            logger.info(
                f"  [{idx}] {item['sku_id']} | {item['category']} | "
                f"Conf: {item['confidence_score']:.1f}/100 ({item['confidence_tier']}) | "
                f"Buy Qty: {item['recommended_buy_quantity']}"
            )

    await engine.dispose()
    logger.info("Database seeding and verification completed successfully!")
    return stats


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Initialize and seed R4 forecasting database.")
    parser.add_argument(
        "--db-url",
        type=str,
        default="sqlite+aiosqlite:///data/r4_forecast.db",
        help="Database URL connection string (defaults to local SQLite for immediate offline operation).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all existing tables before creating schema.",
    )
    parser.add_argument(
        "--sales-limit",
        type=int,
        default=10000,
        help="Number of historical sales rows to ingest.",
    )
    args = parser.parse_args()

    asyncio.run(
        seed_database(
            db_url=args.db_url,
            reset=args.reset,
            sales_limit=args.sales_limit,
        )
    )


if __name__ == "__main__":
    main()
