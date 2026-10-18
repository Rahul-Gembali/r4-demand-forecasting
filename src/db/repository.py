"""Repository pattern implementation for R4 forecasting database operations.

Provides asynchronous, transactional data access for:
- SKUs, store clusters, and holiday calendar
- Weekly historical sales
- Model versions and registered artifacts
- Forecast runs, weekly predictions, and analogue matches
- Inventory recommendations and cluster allocations
- Lineage manifests and confidence ranking queries
"""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    AnalogueMatchModel,
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


class DuplicateRunError(Exception):
    """Raised when attempting to execute or overwrite a completed forecast run."""
    pass


class ForecastRepository:
    """Async repository providing transactional access to R4 database."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # SKU CATALOGUE & REFERENCE DATA
    # =========================================================================

    async def upsert_sku(self, sku_data: dict[str, Any]) -> SKUModel:
        """Create or update a SKU record."""
        sku_id = sku_data["sku_id"]
        stmt = select(SKUModel).where(SKUModel.sku_id == sku_id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            for k, v in sku_data.items():
                if hasattr(existing, k) and k != "sku_id":
                    setattr(existing, k, v)
            return existing
        else:
            new_sku = SKUModel(**sku_data)
            self.session.add(new_sku)
            return new_sku

    async def bulk_upsert_skus(self, skus_data: list[dict[str, Any]]) -> int:
        """Insert or update multiple SKUs."""
        count = 0
        for item in skus_data:
            await self.upsert_sku(item)
            count += 1
        await self.session.flush()
        return count

    async def get_sku(self, sku_id: str) -> SKUModel | None:
        """Retrieve SKU by primary ID."""
        stmt = select(SKUModel).where(SKUModel.sku_id == sku_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_skus(
        self,
        is_evaluation_sku: bool | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SKUModel], int]:
        """List SKUs with optional filtering and pagination."""
        query = select(SKUModel)
        count_query = select(func.count()).select_from(SKUModel)

        if is_evaluation_sku is not None:
            query = query.where(SKUModel.is_evaluation_sku == is_evaluation_sku)
            count_query = count_query.where(SKUModel.is_evaluation_sku == is_evaluation_sku)
        if category is not None:
            query = query.where(SKUModel.category == category)
            count_query = count_query.where(SKUModel.category == category)

        total_res = await self.session.execute(count_query)
        total = total_res.scalar_one()

        query = query.order_by(SKUModel.sku_id).limit(limit).offset(offset)
        items_res = await self.session.execute(query)
        items = list(items_res.scalars().all())

        return items, total

    async def bulk_insert_store_clusters(self, clusters_data: list[dict[str, Any]]) -> int:
        """Insert store cluster entities."""
        count = 0
        for item in clusters_data:
            stmt = select(StoreClusterModel).where(StoreClusterModel.cluster_id == item["cluster_id"])
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if not existing:
                cluster = StoreClusterModel(**item)
                self.session.add(cluster)
                count += 1
        await self.session.flush()
        return count

    async def list_store_clusters(self) -> list[StoreClusterModel]:
        """Fetch all store clusters."""
        stmt = select(StoreClusterModel).order_by(StoreClusterModel.cluster_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def bulk_insert_holidays(self, holidays_data: list[dict[str, Any]]) -> int:
        """Insert holiday records."""
        count = 0
        for item in holidays_data:
            stmt = select(HolidayModel).where(
                HolidayModel.holiday_name == item["holiday_name"],
                HolidayModel.holiday_date == item["holiday_date"],
            )
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if not existing:
                h = HolidayModel(**item)
                self.session.add(h)
                count += 1
        await self.session.flush()
        return count

    async def bulk_insert_weekly_sales(self, sales_records: list[dict[str, Any]]) -> int:
        """Insert historical weekly sales records."""
        models = [WeeklySalesModel(**rec) for rec in sales_records]
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    # =========================================================================
    # MODEL VERSIONS & RUN REGISTRY
    # =========================================================================

    async def create_model_version(self, model_data: dict[str, Any]) -> ModelVersionModel:
        """Register or retrieve an ML model version."""
        model_id = model_data["model_id"]
        stmt = select(ModelVersionModel).where(ModelVersionModel.model_id == model_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            for k, v in model_data.items():
                if hasattr(existing, k) and k != "model_id":
                    setattr(existing, k, v)
            return existing
        model = ModelVersionModel(**model_data)
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_model_version(self, model_id: str) -> ModelVersionModel | None:
        """Fetch model version record by ID."""
        stmt = select(ModelVersionModel).where(ModelVersionModel.model_id == model_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_forecast_run(
        self,
        run_data: dict[str, Any],
        prevent_duplicates: bool = True,
    ) -> ForecastRunModel:
        """Create a new forecast run with optional duplicate-execution protection."""
        run_id = run_data["run_id"]
        stmt = select(ForecastRunModel).where(ForecastRunModel.run_id == run_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing:
            if prevent_duplicates and existing.status == "COMPLETED":
                raise DuplicateRunError(
                    f"Forecast run '{run_id}' has already COMPLETED. "
                    "Duplicate execution blocked to preserve audit trail."
                )
            # If pending, failed, or overwrite allowed, update parameters
            for k, v in run_data.items():
                if hasattr(existing, k) and k != "run_id":
                    setattr(existing, k, v)
            await self.session.flush()
            return existing

        run = ForecastRunModel(**run_data)
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_forecast_run_status(
        self,
        run_id: str,
        status: str,
        completed_at: datetime | None = None,
        overall_wape: float | None = None,
        overall_bias_pct: float | None = None,
        execution_metadata: dict[str, Any] | None = None,
    ) -> ForecastRunModel:
        """Update the lifecycle state and metrics of a forecast run."""
        stmt = select(ForecastRunModel).where(ForecastRunModel.run_id == run_id)
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if not run:
            raise ValueError(f"Forecast run '{run_id}' does not exist.")

        run.status = status
        if completed_at is not None:
            run.completed_at = completed_at
        elif status == "COMPLETED" and run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)

        if overall_wape is not None:
            run.overall_wape = overall_wape
        if overall_bias_pct is not None:
            run.overall_bias_pct = overall_bias_pct
        if execution_metadata is not None:
            run.execution_metadata = execution_metadata

        await self.session.flush()
        return run

    async def get_forecast_run(self, run_id: str) -> ForecastRunModel | None:
        """Retrieve a forecast run with its associated model version."""
        stmt = (
            select(ForecastRunModel)
            .where(ForecastRunModel.run_id == run_id)
            .options(selectinload(ForecastRunModel.model_version))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_forecast_runs(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ForecastRunModel], int]:
        """List forecast runs ordered newest first with total count."""
        count_stmt = select(func.count()).select_from(ForecastRunModel)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(ForecastRunModel)
            .order_by(ForecastRunModel.created_at.desc())
            .options(selectinload(ForecastRunModel.model_version))
            .limit(limit)
            .offset(offset)
        )
        runs = list((await self.session.execute(stmt)).scalars().all())
        return runs, total

    async def delete_forecast_run(self, run_id: str) -> bool:
        """Delete a forecast run and cascade delete its forecasts and recommendations."""
        stmt = select(ForecastRunModel).where(ForecastRunModel.run_id == run_id)
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if not run:
            return False
        await self.session.delete(run)
        await self.session.flush()
        return True

    # =========================================================================
    # FORECASTS & ANALOGUE PERSISTENCE
    # =========================================================================

    async def save_weekly_forecasts(
        self,
        run_id: str,
        forecasts: list[dict[str, Any]],
    ) -> int:
        """Persist weekly point predictions and conformal intervals."""
        models = []
        for f in forecasts:
            models.append(
                WeeklyForecastModel(
                    run_id=run_id,
                    sku_id=f["sku_id"],
                    horizon_week=int(f["horizon_week"]),
                    predicted_sales=float(f["predicted_sales"]),
                    lower_bound_80=f.get("lower_bound_80"),
                    upper_bound_80=f.get("upper_bound_80"),
                    lower_bound_90=f.get("lower_bound_90"),
                    upper_bound_90=f.get("upper_bound_90"),
                )
            )
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    async def save_analogue_matches(
        self,
        run_id: str,
        matches: list[dict[str, Any]],
    ) -> int:
        """Persist top-K analogue retrieval records."""
        models = []
        for m in matches:
            models.append(
                AnalogueMatchModel(
                    run_id=run_id,
                    query_sku_id=m["query_sku_id"],
                    analogue_sku_id=m["analogue_sku_id"],
                    rank=int(m["rank"]),
                    similarity_score=float(m["similarity_score"]),
                    observed_curve=m.get("observed_curve"),
                )
            )
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    # =========================================================================
    # INVENTORY RECOMMENDATIONS & ALLOCATIONS
    # =========================================================================

    async def save_inventory_recommendations(
        self,
        run_id: str,
        recommendations: list[dict[str, Any]],
    ) -> int:
        """Persist initial inventory recommendations and cost evaluations."""
        models = []
        for r in recommendations:
            models.append(
                InventoryRecommendationModel(
                    run_id=run_id,
                    sku_id=r["sku_id"],
                    scenario=r.get("scenario", "BASE"),
                    forecast_cumulative_8w=float(r["forecast_cumulative_8w"]),
                    recommended_buy_quantity=int(r["recommended_buy_quantity"]),
                    unconstrained_quantity=float(r.get("unconstrained_quantity", r["recommended_buy_quantity"])),
                    critical_ratio=float(r["critical_ratio"]),
                    understock_cost_cu=float(r["understock_cost_cu"]),
                    overstock_cost_co=float(r["overstock_cost_co"]),
                    expected_shortage_units=float(r.get("expected_shortage_units", 0.0)),
                    expected_excess_units=float(r.get("expected_excess_units", 0.0)),
                    expected_total_cost=float(r.get("expected_total_cost", 0.0)),
                    expected_fill_rate_pct=float(r.get("expected_fill_rate_pct", 0.0)),
                    confidence_score=r.get("confidence_score"),
                    confidence_tier=r.get("confidence_tier"),
                    explanation_summary=r.get("explanation_summary"),
                    assumptions=r.get("assumptions"),
                )
            )
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    async def save_cluster_allocations(
        self,
        recommendation_id: int,
        sku_id: str,
        allocations: list[dict[str, Any]],
    ) -> int:
        """Persist store-cluster inventory allocations."""
        models = []
        for a in allocations:
            models.append(
                ClusterAllocationModel(
                    recommendation_id=recommendation_id,
                    sku_id=sku_id,
                    cluster_id=a["cluster_id"],
                    allocated_quantity=int(a["allocated_quantity"]),
                    allocation_weight=float(a["allocation_weight"]),
                )
            )
        self.session.add_all(models)
        await self.session.flush()
        return len(models)

    # =========================================================================
    # DATA MANIFESTS & AUDIT LINEAGE
    # =========================================================================

    async def record_data_manifest(self, manifest_data: dict[str, Any]) -> DataManifestModel:
        """Record file checksum and data schema snapshot."""
        manifest = DataManifestModel(**manifest_data)
        self.session.add(manifest)
        await self.session.flush()
        return manifest

    async def get_manifest_by_checksum(self, sha256_checksum: str) -> DataManifestModel | None:
        """Look up manifest entry by SHA256 checksum."""
        stmt = select(DataManifestModel).where(DataManifestModel.sha256_checksum == sha256_checksum)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    # =========================================================================
    # COMPREHENSIVE QUERY INTERFACES
    # =========================================================================

    async def get_sku_forecast(self, run_id: str, sku_id: str) -> dict[str, Any] | None:
        """Fetch comprehensive prediction package for a single SKU in a forecast run."""
        sku = await self.get_sku(sku_id)
        if not sku:
            return None

        # Weekly forecasts
        fc_stmt = (
            select(WeeklyForecastModel)
            .where(
                WeeklyForecastModel.run_id == run_id,
                WeeklyForecastModel.sku_id == sku_id,
            )
            .order_by(WeeklyForecastModel.horizon_week)
        )
        forecasts = list((await self.session.execute(fc_stmt)).scalars().all())

        # Inventory recommendation
        rec_stmt = (
            select(InventoryRecommendationModel)
            .where(
                InventoryRecommendationModel.run_id == run_id,
                InventoryRecommendationModel.sku_id == sku_id,
            )
        )
        rec = (await self.session.execute(rec_stmt)).scalar_one_or_none()

        # Analogues
        an_stmt = (
            select(AnalogueMatchModel)
            .where(
                AnalogueMatchModel.run_id == run_id,
                AnalogueMatchModel.query_sku_id == sku_id,
            )
            .order_by(AnalogueMatchModel.rank)
        )
        analogues = list((await self.session.execute(an_stmt)).scalars().all())

        return {
            "sku_id": sku.sku_id,
            "product_name": sku.product_name,
            "category": sku.category,
            "subcategory": sku.subcategory,
            "colour": sku.colour,
            "material": sku.material,
            "base_price": float(sku.base_price),
            "brand": sku.brand,
            "brand_tier": sku.brand_tier,
            "launch_date": sku.launch_date.isoformat(),
            "has_marketing_support": sku.has_marketing_support,
            "is_evaluation_sku": sku.is_evaluation_sku,
            "forecasts": [
                {
                    "horizon_week": f.horizon_week,
                    "predicted_sales": float(f.predicted_sales),
                    "lower_bound_80": float(f.lower_bound_80) if f.lower_bound_80 is not None else None,
                    "upper_bound_80": float(f.upper_bound_80) if f.upper_bound_80 is not None else None,
                    "lower_bound_90": float(f.lower_bound_90) if f.lower_bound_90 is not None else None,
                    "upper_bound_90": float(f.upper_bound_90) if f.upper_bound_90 is not None else None,
                }
                for f in forecasts
            ],
            "recommendation": (
                {
                    "scenario": rec.scenario,
                    "forecast_cumulative_8w": float(rec.forecast_cumulative_8w),
                    "recommended_buy_quantity": rec.recommended_buy_quantity,
                    "critical_ratio": float(rec.critical_ratio),
                    "understock_cost_cu": float(rec.understock_cost_cu),
                    "overstock_cost_co": float(rec.overstock_cost_co),
                    "expected_shortage_units": float(rec.expected_shortage_units),
                    "expected_excess_units": float(rec.expected_excess_units),
                    "expected_total_cost": float(rec.expected_total_cost),
                    "expected_fill_rate_pct": float(rec.expected_fill_rate_pct),
                    "confidence_score": float(rec.confidence_score) if rec.confidence_score is not None else None,
                    "confidence_tier": rec.confidence_tier,
                    "explanation_summary": rec.explanation_summary,
                    "assumptions": rec.assumptions,
                }
                if rec
                else None
            ),
            "analogues": [
                {
                    "rank": a.rank,
                    "analogue_sku_id": a.analogue_sku_id,
                    "similarity_score": float(a.similarity_score),
                    "observed_curve": a.observed_curve,
                }
                for a in analogues
            ],
        }

    async def get_least_confident_skus(
        self,
        run_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve the least-confident products for a run, ordered by confidence score ASC."""
        stmt = (
            select(InventoryRecommendationModel, SKUModel)
            .join(SKUModel, InventoryRecommendationModel.sku_id == SKUModel.sku_id)
            .where(
                InventoryRecommendationModel.run_id == run_id,
                InventoryRecommendationModel.confidence_score.is_not(None),
            )
            .order_by(InventoryRecommendationModel.confidence_score.asc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        results = []
        for rec, sku in rows:
            results.append(
                {
                    "sku_id": sku.sku_id,
                    "product_name": sku.product_name,
                    "category": sku.category,
                    "subcategory": sku.subcategory,
                    "base_price": float(sku.base_price),
                    "confidence_score": float(rec.confidence_score),
                    "confidence_tier": rec.confidence_tier,
                    "forecast_cumulative_8w": float(rec.forecast_cumulative_8w),
                    "recommended_buy_quantity": rec.recommended_buy_quantity,
                    "explanation_summary": rec.explanation_summary,
                    "assumptions": rec.assumptions,
                }
            )
        return results

    async def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        """Calculate executive metrics and totals for a forecast run."""
        run = await self.get_forecast_run(run_id)
        if not run:
            return None

        # Aggregations over recommendations
        rec_stmt = (
            select(
                func.count(InventoryRecommendationModel.id).label("total_skus"),
                func.sum(InventoryRecommendationModel.recommended_buy_quantity).label("total_buy_units"),
                func.sum(InventoryRecommendationModel.expected_total_cost).label("total_expected_cost"),
                func.avg(InventoryRecommendationModel.confidence_score).label("avg_confidence_score"),
                func.avg(InventoryRecommendationModel.expected_fill_rate_pct).label("avg_fill_rate_pct"),
            )
            .where(InventoryRecommendationModel.run_id == run_id)
        )
        rec_row = (await self.session.execute(rec_stmt)).one()

        return {
            "run_id": run.run_id,
            "model_id": run.model_id,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "sku_count": run.sku_count,
            "overall_wape": float(run.overall_wape) if run.overall_wape is not None else None,
            "overall_bias_pct": float(run.overall_bias_pct) if run.overall_bias_pct is not None else None,
            "total_recommended_buy_units": int(rec_row.total_buy_units or 0),
            "total_expected_cost": float(rec_row.total_expected_cost or 0.0),
            "average_confidence_score": float(rec_row.avg_confidence_score or 0.0),
            "average_fill_rate_pct": float(rec_row.avg_fill_rate_pct or 0.0),
        }
