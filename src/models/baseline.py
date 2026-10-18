"""Category-level and hierarchical launch curve baseline models."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from src.core.logging import logger


class FallbackLevel(StrEnum):
    CATEGORY_SUBCATEGORY = "CATEGORY_SUBCATEGORY"
    CATEGORY = "CATEGORY"
    GLOBAL = "GLOBAL"


@dataclass
class BaselinePredictionResult:
    """Forecast output for a single SKU across weeks 1-8."""
    sku_id: str
    weekly_forecast: list[float]  # Length 8: W1 to W8
    fallback_level: FallbackLevel
    donor_sku_count: int
    aggregation_method: str
    hierarchy_key: str


class LaunchCurveBaseline:
    """Hierarchical empirical launch curve model with robust aggregations and fallback.

    Hierarchy:
      Level 1: (category, subcategory) if distinct donor SKUs >= min_donor_skus
      Level 2: (category) if distinct donor SKUs >= min_donor_skus
      Level 3: Global historical launch curve
    """

    def __init__(
        self,
        min_donor_skus: int = 5,
        aggregation_method: str = "median",  # median, mean, trimmed_mean
        trimmed_mean_percentile: float = 0.10,
    ):
        self.min_donor_skus = min_donor_skus
        self.aggregation_method = aggregation_method
        self.trimmed_mean_percentile = trimmed_mean_percentile

        # Fitted curve storage: mapping key -> list of 8 floats
        self.subcat_curves: dict[tuple[str, str], list[float]] = {}
        self.subcat_donor_counts: dict[tuple[str, str], int] = {}

        self.category_curves: dict[str, list[float]] = {}
        self.category_donor_counts: dict[str, int] = {}

        self.global_curve: list[float] = [0.0] * 8
        self.global_donor_count: int = 0
        self.is_fitted: bool = False

    def _aggregate_series(self, series: pd.Series) -> float:
        """Aggregates a distribution of sales values using the configured method."""
        clean = series.dropna().to_numpy()
        if len(clean) == 0:
            return 0.0

        if self.aggregation_method == "median":
            val = float(np.median(clean))
        elif self.aggregation_method == "trimmed_mean":
            low_p = np.percentile(clean, self.trimmed_mean_percentile * 100.0)
            high_p = np.percentile(clean, (1.0 - self.trimmed_mean_percentile) * 100.0)
            trimmed = clean[(clean >= low_p) & (clean <= high_p)]
            val = float(np.mean(trimmed)) if len(trimmed) > 0 else float(np.mean(clean))
        else:  # default to mean
            val = float(np.mean(clean))

        return max(0.0, round(val, 2))

    def fit(self, df_train_features: pd.DataFrame) -> "LaunchCurveBaseline":
        """Fits launch curves from training features containing W1 to W8 observations.

        Expects df_train_features with columns:
        ['sku_id', 'launch_week_age', 'category', 'subcategory', 'units_sold']
        """
        logger.info("Fitting LaunchCurveBaseline on %d records...", len(df_train_features))

        # 1. Aggregate to SKU-level total enterprise sales per launch week
        sku_week = (
            df_train_features.groupby(["sku_id", "launch_week_age", "category", "subcategory"])[
                "units_sold"
            ]
            .sum()
            .reset_index()
        )

        # 2. Global curve
        self.global_donor_count = int(sku_week["sku_id"].nunique())
        global_curve = []
        for w in range(1, 9):
            w_sales = sku_week[sku_week["launch_week_age"] == w]["units_sold"]
            global_curve.append(self._aggregate_series(w_sales))
        self.global_curve = global_curve

        # 3. Category curves
        self.category_curves.clear()
        self.category_donor_counts.clear()
        for cat, cat_group in sku_week.groupby("category"):
            distinct_skus = int(cat_group["sku_id"].nunique())
            self.category_donor_counts[str(cat)] = distinct_skus
            c_curve = []
            for w in range(1, 9):
                w_sales = cat_group[cat_group["launch_week_age"] == w]["units_sold"]
                c_curve.append(self._aggregate_series(w_sales))
            self.category_curves[str(cat)] = c_curve

        # 4. Category + Subcategory curves
        self.subcat_curves.clear()
        self.subcat_donor_counts.clear()
        for (cat, subcat), subcat_group in sku_week.groupby(["category", "subcategory"]):
            distinct_skus = int(subcat_group["sku_id"].nunique())
            self.subcat_donor_counts[(str(cat), str(subcat))] = distinct_skus
            sc_curve = []
            for w in range(1, 9):
                w_sales = subcat_group[subcat_group["launch_week_age"] == w]["units_sold"]
                sc_curve.append(self._aggregate_series(w_sales))
            self.subcat_curves[(str(cat), str(subcat))] = sc_curve

        self.is_fitted = True
        logger.info(
            "LaunchCurveBaseline fitted: %d categories, %d subcategories, %d global SKUs.",
            len(self.category_curves),
            len(self.subcat_curves),
            self.global_donor_count,
        )
        return self

    def predict_sku(self, category: str, subcategory: str | None, sku_id: str = "UNKNOWN") -> BaselinePredictionResult:
        """Generates 8-week nonnegative point forecast for a single SKU with fallback."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict_sku() can be called.")

        cat_str = str(category).strip()
        subcat_str = str(subcategory).strip() if subcategory else "missing"

        # Check Level 1: Category + Subcategory
        subcat_key = (cat_str, subcat_str)
        if subcat_key in self.subcat_curves:
            donor_count = self.subcat_donor_counts.get(subcat_key, 0)
            if donor_count >= self.min_donor_skus:
                return BaselinePredictionResult(
                    sku_id=sku_id,
                    weekly_forecast=self.subcat_curves[subcat_key].copy(),
                    fallback_level=FallbackLevel.CATEGORY_SUBCATEGORY,
                    donor_sku_count=donor_count,
                    aggregation_method=self.aggregation_method,
                    hierarchy_key=f"{cat_str} / {subcat_str}",
                )

        # Check Level 2: Category
        if cat_str in self.category_curves:
            donor_count = self.category_donor_counts.get(cat_str, 0)
            if donor_count >= self.min_donor_skus:
                return BaselinePredictionResult(
                    sku_id=sku_id,
                    weekly_forecast=self.category_curves[cat_str].copy(),
                    fallback_level=FallbackLevel.CATEGORY,
                    donor_sku_count=donor_count,
                    aggregation_method=self.aggregation_method,
                    hierarchy_key=cat_str,
                )

        # Level 3: Global Fallback
        return BaselinePredictionResult(
            sku_id=sku_id,
            weekly_forecast=self.global_curve.copy(),
            fallback_level=FallbackLevel.GLOBAL,
            donor_sku_count=self.global_donor_count,
            aggregation_method=self.aggregation_method,
            hierarchy_key="GLOBAL",
        )

    def predict_dataframe(self, df_target_attributes: pd.DataFrame) -> pd.DataFrame:
        """Generates 8-week forecasts for a dataframe of target SKUs.

        Returns long-form submission dataframe:
        ['sku_id', 'horizon_week', 'predicted_sales', 'fallback_level', 'donor_sku_count', 'hierarchy_key']
        """
        records = []
        unique_skus = df_target_attributes.drop_duplicates(subset=["sku_id"])

        for _, row in unique_skus.iterrows():
            sku_id = str(row["sku_id"])
            cat = str(row.get("category", "_UNKNOWN_"))
            subcat = str(row.get("subcategory", "missing"))

            res = self.predict_sku(cat, subcat, sku_id=sku_id)
            for w_idx, pred_val in enumerate(res.weekly_forecast, start=1):
                records.append({
                    "sku_id": sku_id,
                    "horizon_week": w_idx,
                    "predicted_sales": max(0.0, float(pred_val)),
                    "fallback_level": res.fallback_level.value,
                    "donor_sku_count": res.donor_sku_count,
                    "hierarchy_key": res.hierarchy_key,
                })

        return pd.DataFrame(records)
