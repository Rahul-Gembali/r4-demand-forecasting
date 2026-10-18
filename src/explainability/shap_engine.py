"""TreeSHAP Explanation Engine for CatBoost Demand Forecasting.

Extracts exact TreeSHAP feature contributions across introductory weeks 1 through 8,
distinguishes positive vs negative drivers, and computes cumulative 8-week impacts.
"""

from dataclasses import dataclass

import catboost as cb
import numpy as np
import pandas as pd

from src.models.supervised import CatBoostForecaster


@dataclass
class SKUFeatureContribution:
    """SHAP-derived feature contribution breakdown for a single SKU."""
    sku_id: str
    base_value: float                      # Global expected value in log1p model space
    cumulative_shap_values: dict[str, float] # Net feature contributions summed across 8 weeks
    weekly_shap_values: list[dict[str, float]] # Length 8: per-week SHAP contributions
    positive_drivers: list[tuple[str, float]] # Top features increasing forecast above baseline
    negative_drivers: list[tuple[str, float]] # Top features decreasing forecast below baseline


class TreeShapEngine:
    """Computes exact TreeSHAP values for CatBoost forecaster."""

    def __init__(self, forecaster: CatBoostForecaster):
        if not forecaster.is_fitted or forecaster.model is None:
            raise RuntimeError("Forecaster must be fitted before computing SHAP values.")
        self.forecaster = forecaster
        self.feature_columns = forecaster.feature_columns
        self.categorical_columns = forecaster.categorical_columns

    def explain_sku_weeks(self, df_sku_8w: pd.DataFrame) -> SKUFeatureContribution:
        """Computes TreeSHAP feature attributions for all 8 weeks of a SKU.

        Parameters
        ----------
        df_sku_8w : pd.DataFrame
            Must contain exactly 8 rows corresponding to launch_week_age 1 through 8.
        """
        if len(df_sku_8w) != 8:
            raise ValueError(f"Expected exactly 8 rows for 8-week horizon, got {len(df_sku_8w)}")

        sku_id = str(df_sku_8w["sku_id"].iloc[0])
        X = self.forecaster.prepare_features(df_sku_8w)
        pool = cb.Pool(X, cat_features=self.categorical_columns)

        # ShapValues has shape (8, n_features + 1), where last column is base value
        raw_shaps = self.forecaster.model.get_feature_importance(data=pool, type="ShapValues")

        base_val = float(raw_shaps[0, -1])
        weekly_shaps: list[dict[str, float]] = []

        for w_idx in range(8):
            w_dict = {
                col: round(float(raw_shaps[w_idx, col_idx]), 4)
                for col_idx, col in enumerate(self.feature_columns)
            }
            weekly_shaps.append(w_dict)

        # Net cumulative 8-week contributions (summed across all 8 weeks)
        cumul_shaps: dict[str, float] = {}
        for col in self.feature_columns:
            cumul_shaps[col] = round(float(np.sum(raw_shaps[:, self.feature_columns.index(col)])), 4)

        # Rank drivers by cumulative magnitude
        sorted_drivers = sorted(cumul_shaps.items(), key=lambda item: abs(item[1]), reverse=True)
        pos_drivers = [(k, v) for k, v in sorted_drivers if v > 0.0]
        neg_drivers = [(k, v) for k, v in sorted_drivers if v < 0.0]

        return SKUFeatureContribution(
            sku_id=sku_id,
            base_value=round(base_val, 4),
            cumulative_shap_values=cumul_shaps,
            weekly_shap_values=weekly_shaps,
            positive_drivers=pos_drivers[:5],
            negative_drivers=neg_drivers[:5],
        )
