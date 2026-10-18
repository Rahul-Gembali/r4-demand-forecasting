"""End-to-End Data Pipeline for R4 Cold-Start Demand Forecasting.

Handles ingestion, normalization, launch-age alignment, feature engineering,
leakage fencing, data quality auditing, and versioned manifest generation.
"""

from datetime import datetime, timedelta
import math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from src.core.config import settings
from src.core.logging import logger
from src.data.manifest import DataManifest, ManifestGenerator
from src.data.quality import DataQualityAuditor, DataQualityConfig, QualityAuditReport
from src.data.schema import BrandTier, ObservationStatus, PriceBand


class DataPipeline:
    """Production-grade data ingestion, validation, and feature generation pipeline."""

    def __init__(
        self,
        raw_dir: Path | str | None = None,
        interim_dir: Path | str | None = None,
        processed_dir: Path | str | None = None,
        config: DataQualityConfig | None = None,
    ):
        self.raw_dir = Path(raw_dir or settings.data_raw_dir)
        self.interim_dir = Path(interim_dir or settings.data_interim_dir)
        self.processed_dir = Path(processed_dir or settings.data_processed_dir)
        self.config = config or DataQualityConfig()

        self.auditor = DataQualityAuditor(self.config)
        self.manifest_gen = ManifestGenerator()

        # State tracking for consistent train/inference transforms
        self.known_categories: set[str] = set()
        self.known_subcategories: set[str] = set()
        self.known_colours: set[str] = set()
        self.known_materials: set[str] = set()
        self.known_brands: set[str] = set()
        self.training_median_price: float = 49.99

    # ==========================================================================
    # Step 1: Raw Ingestion and Normalization
    # ==========================================================================

    def load_raw_tables(self) -> dict[str, pd.DataFrame]:
        """Loads and normalizes raw tabular files without mutating sources."""
        logger.info("Loading raw datasets from: %s", self.raw_dir)

        # 1. Historical Sales
        sales_path = self.raw_dir / "historical_sales.csv"
        if not sales_path.exists():
            raise FileNotFoundError(f"Missing required raw file: {sales_path}")
        df_sales = pd.read_csv(sales_path, low_memory=False)

        # 2. Mature SKU Attributes
        mature_attr_path = self.raw_dir / "mature_sku_attributes.csv"
        if not mature_attr_path.exists():
            raise FileNotFoundError(f"Missing required raw file: {mature_attr_path}")
        df_mature = pd.read_csv(mature_attr_path, low_memory=False)

        # 3. New Target SKU Attributes (150 SKUs)
        new_attr_path = self.raw_dir / "new_sku_attributes.csv"
        if not new_attr_path.exists():
            raise FileNotFoundError(f"Missing required raw file: {new_attr_path}")
        df_new = pd.read_csv(new_attr_path, low_memory=False)

        # 4. Store Clusters
        stores_path = self.raw_dir / "store_clusters.csv"
        if not stores_path.exists():
            raise FileNotFoundError(f"Missing required raw file: {stores_path}")
        df_stores = pd.read_csv(stores_path, low_memory=False)

        # 5. Holiday Calendar
        calendar_path = self.raw_dir / "holiday_calendar.csv"
        if not calendar_path.exists():
            raise FileNotFoundError(f"Missing required raw file: {calendar_path}")
        df_calendar = pd.read_csv(calendar_path, low_memory=False)

        return {
            "sales": self._normalize_sales(df_sales),
            "mature_attributes": self._normalize_attributes(df_mature, is_target_eval=False),
            "new_attributes": self._normalize_attributes(df_new, is_target_eval=True),
            "stores": self._normalize_stores(df_stores),
            "calendar": self._normalize_calendar(df_calendar),
        }

    def _normalize_sales(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes sales dates, types, and checks duplicates."""
        df = df.copy()
        df["sku_id"] = df["sku_id"].astype(str).str.strip()
        df["store_id"] = df["store_id"].astype(str).str.strip()
        df["week_start_date"] = pd.to_datetime(df["week_start_date"]).dt.strftime("%Y-%m-%d")
        df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0.0)
        df["units_sold"] = np.maximum(0.0, df["units_sold"])

        # Check stockout columns without inventing
        if "days_in_stock" in df.columns:
            df["days_in_stock"] = pd.to_numeric(df["days_in_stock"], errors="coerce")
        else:
            df["days_in_stock"] = np.nan

        # Deduplicate on composite primary key
        pk_cols = ["sku_id", "store_id", "week_start_date"]
        dups = df.duplicated(subset=pk_cols, keep="first")
        if dups.any():
            logger.warning("Found %d duplicate sales records. Deduplicating.", dups.sum())
            df = df.drop_duplicates(subset=pk_cols, keep="first")

        return df

    def _normalize_attributes(self, df: pd.DataFrame, is_target_eval: bool) -> pd.DataFrame:
        """Normalizes product catalog attributes."""
        df = df.copy()
        df["sku_id"] = df["sku_id"].astype(str).str.strip()
        df["category"] = df["category"].astype(str).str.strip()
        df["subcategory"] = df.get("subcategory", pd.Series(["missing"] * len(df))).fillna("missing").astype(str).str.strip()
        df["colour"] = df.get("colour", pd.Series(["missing"] * len(df))).fillna("missing").astype(str).str.strip()
        df["material"] = df.get("material", pd.Series(["missing"] * len(df))).fillna("missing").astype(str).str.strip()
        df["brand"] = df.get("brand", pd.Series(["generic"] * len(df))).fillna("generic").astype(str).str.strip()
        df["brand_tier"] = df.get("brand_tier", pd.Series(["Tier 2 Regional"] * len(df))).fillna("Tier 2 Regional").astype(str).str.strip()
        df["base_price"] = pd.to_numeric(df["base_price"], errors="coerce")
        df["launch_date"] = pd.to_datetime(df["launch_date"]).dt.strftime("%Y-%m-%d")
        df["has_marketing_support"] = df.get("has_marketing_support", pd.Series([True] * len(df))).astype(bool)
        df["is_target_eval"] = is_target_eval

        # Deduplicate on sku_id
        df = df.drop_duplicates(subset=["sku_id"], keep="first")
        return df

    def _normalize_stores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes store cluster mappings."""
        df = df.copy()
        df["store_id"] = df["store_id"].astype(str).str.strip()
        df["cluster_id"] = df["cluster_id"].astype(str).str.strip()
        df["region"] = df.get("region", pd.Series(["National"] * len(df))).fillna("National").astype(str).str.strip()
        df["store_tier"] = df.get("store_tier", pd.Series(["Standard"] * len(df))).fillna("Standard").astype(str).str.strip()
        return df.drop_duplicates(subset=["store_id"], keep="first")

    def _normalize_calendar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes holiday calendar."""
        df = df.copy()
        df["week_start_date"] = pd.to_datetime(df["week_start_date"]).dt.strftime("%Y-%m-%d")
        df["fiscal_year"] = pd.to_numeric(df["fiscal_year"]).astype(int)
        df["fiscal_week"] = pd.to_numeric(df["fiscal_week"]).astype(int)
        df["is_holiday_week"] = pd.to_numeric(df["is_holiday_week"]).astype(int)
        df["holiday_name"] = df.get("holiday_name", pd.Series(["None"] * len(df))).fillna("None").astype(str).str.strip()
        return df.drop_duplicates(subset=["week_start_date"], keep="first")

    # ==========================================================================
    # Step 2: Save Interim Representations
    # ==========================================================================

    def save_interim_tables(self, tables: dict[str, pd.DataFrame]) -> None:
        """Persists typed, normalized tables to Parquet store."""
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            out_file = self.interim_dir / f"{name}.parquet"
            df.to_parquet(out_file, index=False)
            logger.info("Saved interim table: %s (%d rows)", out_file, len(df))

    # ==========================================================================
    # Step 3: Feature Engineering & Launch-Age Alignment (W1..W8)
    # ==========================================================================

    def compute_price_band(self, price: float) -> str:
        """Maps unit price to formal price band enum."""
        if price < 25.0:
            return PriceBand.BUDGET.value
        elif price < 75.0:
            return PriceBand.MID_RANGE.value
        elif price < 150.0:
            return PriceBand.PREMIUM.value
        else:
            return PriceBand.LUXURY.value

    def apply_marketing_business_rule(self, has_marketing_support: bool, launch_week_age: int) -> int:
        """Applies validated business rule: marketing burst during introductory W1..W4."""
        if not has_marketing_support:
            return 0
        return 1 if launch_week_age <= self.config.marketing_launch_burst_weeks else 0

    def fit_training_encoders(self, df_mature: pd.DataFrame) -> None:
        """Fits vocabulary and statistics strictly on mature training SKUs."""
        self.known_categories = set(df_mature["category"].dropna().unique())
        self.known_subcategories = set(df_mature["subcategory"].dropna().unique())
        self.known_colours = set(df_mature["colour"].dropna().unique())
        self.known_materials = set(df_mature["material"].dropna().unique())
        self.known_brands = set(df_mature["brand"].dropna().unique())
        self.training_median_price = float(df_mature["base_price"].median())

    def _transform_attributes(self, df_attr: pd.DataFrame) -> pd.DataFrame:
        """Transforms attributes into standard features handling unseen categories."""
        df = df_attr.copy()

        # Price imputation and band
        df["base_price"] = df["base_price"].fillna(self.training_median_price)
        df["price_band"] = df["base_price"].apply(self.compute_price_band)
        df["log_base_price"] = np.log1p(df["base_price"])

        # Handle missing vs unseen categories between train and inference
        df["category"] = df["category"].apply(
            lambda x: "missing" if x == "missing" else (x if x in self.known_categories else "_UNKNOWN_")
        )
        df["subcategory"] = df["subcategory"].apply(
            lambda x: "missing" if x == "missing" else (x if x in self.known_subcategories else "_UNKNOWN_")
        )
        df["colour"] = df["colour"].apply(
            lambda x: "missing" if x == "missing" else (x if x in self.known_colours else "_UNKNOWN_")
        )
        df["material"] = df["material"].apply(
            lambda x: "missing" if x == "missing" else (x if x in self.known_materials else "_UNKNOWN_")
        )
        df["brand"] = df["brand"].apply(
            lambda x: "missing" if x == "missing" else (x if x in self.known_brands else "_UNKNOWN_")
        )

        # Launch month and cyclical transforms
        launch_dt = pd.to_datetime(df["launch_date"])
        df["launch_month"] = launch_dt.dt.month
        df["sin_launch_month"] = np.sin(2.0 * math.pi * df["launch_month"] / 12.0).round(6)
        df["cos_launch_month"] = np.cos(2.0 * math.pi * df["launch_month"] / 12.0).round(6)

        return df

    def build_training_features(
        self,
        df_sales: pd.DataFrame,
        df_mature: pd.DataFrame,
        df_stores: pd.DataFrame,
        df_calendar: pd.DataFrame,
    ) -> pd.DataFrame:
        """Builds historical training features aligned to launch week age 1 to 8."""
        logger.info("Building training features for %d mature SKUs...", len(df_mature))
        self.fit_training_encoders(df_mature)
        attr_clean = self._transform_attributes(df_mature)

        # Merge sales with attributes
        sales_with_attr = pd.merge(df_sales, attr_clean, on="sku_id", how="inner")

        # Compute launch week age
        sale_dt = pd.to_datetime(sales_with_attr["week_start_date"])
        launch_dt = pd.to_datetime(sales_with_attr["launch_date"])
        days_diff = (sale_dt - launch_dt).dt.days
        sales_with_attr["launch_week_age"] = (days_diff // 7) + 1

        # Restrict strictly to introductory weeks W1 through W8
        w1_w8 = sales_with_attr[sales_with_attr["launch_week_age"].isin(self.config.expected_horizon_weeks)].copy()

        # Join store clusters
        w1_w8 = pd.merge(w1_w8, df_stores[["store_id", "cluster_id"]], on="store_id", how="left")
        w1_w8["cluster_id"] = w1_w8["cluster_id"].fillna("CLUSTER_UNKNOWN")

        # Join calendar & holidays
        w1_w8 = pd.merge(w1_w8, df_calendar, on="week_start_date", how="left")
        w1_w8["is_holiday_week"] = w1_w8["is_holiday_week"].fillna(0).astype(int)
        w1_w8["holiday_name"] = w1_w8["holiday_name"].fillna("None")

        # Calendar cyclical features
        cal_dt = pd.to_datetime(w1_w8["week_start_date"])
        w1_w8["week_of_year"] = cal_dt.dt.isocalendar().week.astype(int)
        w1_w8["sin_week_of_year"] = np.sin(2.0 * math.pi * w1_w8["week_of_year"] / 52.0).round(6)
        w1_w8["cos_week_of_year"] = np.cos(2.0 * math.pi * w1_w8["week_of_year"] / 52.0).round(6)

        # Apply marketing flag rule
        w1_w8["marketing_flag"] = w1_w8.apply(
            lambda row: self.apply_marketing_business_rule(row["has_marketing_support"], row["launch_week_age"]),
            axis=1,
        )

        # Classify observation status (distinguish genuine zero sales from unobserved)
        w1_w8["observation_status"] = np.where(
            w1_w8["units_sold"] == 0,
            ObservationStatus.GENUINE_ZERO.value,
            ObservationStatus.OBSERVED_POSITIVE.value,
        )
        w1_w8["is_target_eval_sku"] = False

        # Select standard columns
        feature_cols = [
            "sku_id", "store_id", "cluster_id", "launch_week_age",
            "category", "subcategory", "colour", "material",
            "base_price", "log_base_price", "price_band", "brand", "brand_tier",
            "launch_month", "sin_launch_month", "cos_launch_month",
            "marketing_flag", "is_holiday_week", "holiday_name",
            "week_of_year", "sin_week_of_year", "cos_week_of_year",
            "observation_status", "is_target_eval_sku", "units_sold",
        ]
        return w1_w8[feature_cols].copy()

    def build_inference_features(
        self,
        df_new: pd.DataFrame,
        df_stores: pd.DataFrame,
        df_calendar: pd.DataFrame,
    ) -> pd.DataFrame:
        """Builds multi-horizon features for 150 cold-start SKUs with ZERO target leakage."""
        logger.info("Building inference features for %d target evaluation SKUs...", len(df_new))
        attr_clean = self._transform_attributes(df_new)

        records = []
        for _, sku_row in attr_clean.iterrows():
            launch_monday = pd.to_datetime(sku_row["launch_date"])
            for w_age in self.config.expected_horizon_weeks:
                horizon_date = (launch_monday + timedelta(days=(w_age - 1) * 7)).strftime("%Y-%m-%d")
                mkt_flag = self.apply_marketing_business_rule(sku_row["has_marketing_support"], w_age)

                # Fetch holiday for horizon date if exists
                cal_matches = df_calendar[df_calendar["week_start_date"] == horizon_date]
                if not cal_matches.empty:
                    is_h = int(cal_matches.iloc[0]["is_holiday_week"])
                    h_name = str(cal_matches.iloc[0]["holiday_name"])
                else:
                    is_h = 0
                    h_name = "None"

                dt_obj = pd.to_datetime(horizon_date)
                woy = int(dt_obj.isocalendar().week)

                records.append({
                    "sku_id": sku_row["sku_id"],
                    "store_id": "ENTERPRISE_AGG",
                    "cluster_id": "ENTERPRISE_ALL",
                    "launch_week_age": w_age,
                    "category": sku_row["category"],
                    "subcategory": sku_row["subcategory"],
                    "colour": sku_row["colour"],
                    "material": sku_row["material"],
                    "base_price": sku_row["base_price"],
                    "log_base_price": sku_row["log_base_price"],
                    "price_band": sku_row["price_band"],
                    "brand": sku_row["brand"],
                    "brand_tier": sku_row["brand_tier"],
                    "launch_month": sku_row["launch_month"],
                    "sin_launch_month": sku_row["sin_launch_month"],
                    "cos_launch_month": sku_row["cos_launch_month"],
                    "marketing_flag": mkt_flag,
                    "is_holiday_week": is_h,
                    "holiday_name": h_name,
                    "week_of_year": woy,
                    "sin_week_of_year": round(math.sin(2.0 * math.pi * woy / 52.0), 6),
                    "cos_week_of_year": round(math.cos(2.0 * math.pi * woy / 52.0), 6),
                    "observation_status": ObservationStatus.MISSING_OBSERVATION.value,
                    "is_target_eval_sku": True,
                    # STRICT LEAKAGE PREVENTION: units_sold is strictly None during inference
                    "units_sold": None,
                })

        return pd.DataFrame(records)

    # ==========================================================================
    # Step 4: End-to-End Orchestrator
    # ==========================================================================

    def run_pipeline(self) -> tuple[pd.DataFrame, pd.DataFrame, QualityAuditReport, DataManifest]:
        """Runs the complete ingestion, quality audit, and manifest compilation."""
        # 1. Ingest raw tables
        raw_tables = self.load_raw_tables()

        # 2. Persist interim tables
        self.save_interim_tables(raw_tables)

        # 3. Build features
        train_df = self.build_training_features(
            raw_tables["sales"],
            raw_tables["mature_attributes"],
            raw_tables["stores"],
            raw_tables["calendar"],
        )
        inference_df = self.build_inference_features(
            raw_tables["new_attributes"],
            raw_tables["stores"],
            raw_tables["calendar"],
        )

        # 4. Save processed features
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        train_path = self.processed_dir / "train_features.parquet"
        inference_path = self.processed_dir / "inference_features.parquet"
        train_df.to_parquet(train_path, index=False)
        inference_df.to_parquet(inference_path, index=False)
        logger.info("Saved processed train features: %s (%d rows)", train_path, len(train_df))
        logger.info("Saved processed inference features: %s (%d rows)", inference_path, len(inference_df))

        # 5. Quality Audit & Leakage Check
        quality_report = self.auditor.audit_processed_features(train_df, inference_df)
        self.auditor.save_reports(
            quality_report,
            Path("docs/data_quality_report.json"),
            Path("docs/DATA_QUALITY_REPORT.md"),
        )
        logger.info("Data Quality Audit Status: %s", quality_report.overall_status)

        # 6. Versioned Data Manifest
        manifest = DataManifest(
            metadata={
                "train_skus": int(train_df["sku_id"].nunique()),
                "target_eval_skus": int(inference_df["sku_id"].nunique()),
                "horizon_weeks": self.config.expected_horizon_weeks,
                "leakage_check_passed": quality_report.leakage_check_passed,
            },
            feature_schema={col: str(dtype) for col, dtype in train_df.dtypes.items()},
        )
        # Register raw files
        for f in self.raw_dir.glob("*.csv"):
            manifest.source_raw_files.append(self.manifest_gen.create_manifest_item(f))
        # Register interim files
        for f in self.interim_dir.glob("*.parquet"):
            manifest.interim_files.append(self.manifest_gen.create_manifest_item(f))
        # Register processed files
        manifest.processed_files.append(self.manifest_gen.create_manifest_item(train_path, train_df))
        manifest.processed_files.append(self.manifest_gen.create_manifest_item(inference_path, inference_df))

        manifest_path = self.processed_dir / "data_manifest.json"
        self.manifest_gen.save_manifest(manifest, manifest_path)
        logger.info("Generated versioned data manifest: %s", manifest_path)

        return train_df, inference_df, quality_report, manifest
