"""Official Evaluation Engine for R4 New Product Demand Forecasting.

Strictly adheres to docs/EVALUATION_SPEC.md:
- Implements exact enterprise WAPE, per-week WAPE, RMSE, MAE, Forecast Bias %.
- Robust handling of zero denominators and edge cases.
- Comprehensive prediction interval evaluation (Coverage, Mean Width, Winkler Score).
- Category-level breakdown and category stability metrics.
- Submission integrity and schema validation for 150 evaluation SKUs.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from src.evaluation.metrics import (
    forecast_bias_pct,
    mae,
    rmse,
    wape,
)
from src.evaluation.uncertainty import (
    empirical_coverage,
    mean_interval_width,
    winkler_score,
)


@dataclass
class OfficialEvaluationReport:
    """Structured report returned by the official evaluation engine."""
    evaluation_timestamp: str
    total_skus: int
    total_horizon_points: int
    overall_wape: float
    overall_rmse: float
    overall_mae: float
    overall_bias_pct: float
    weekly_wape: dict[int, float]
    cumulative_8w_wape: float
    cumulative_8w_rmse: float
    cumulative_8w_mae: float
    cumulative_8w_bias_pct: float
    category_wape: dict[str, float]
    category_stability_std: float
    interval_evaluation: dict[str, Any] = field(default_factory=dict)
    validation_status: str = "PASSED"
    notes: list[str] = field(default_factory=list)


class OfficialEvaluator:
    """Official Evaluator matching R4 competition specification."""

    EXPECTED_SKU_COUNT = 150
    EXPECTED_HORIZON_WEEKS = set(range(1, 9))
    EXPECTED_TOTAL_ROWS = 1200

    REQUIRED_PRED_COLS = {"sku_id", "horizon_week", "predicted_sales"}
    REQUIRED_TRUTH_COLS = {"sku_id", "horizon_week", "actual_sales"}

    def __init__(self, target_sku_count: int = 150, strict_row_count: bool = False):
        self.target_sku_count = target_sku_count
        self.strict_row_count = strict_row_count

    def validate_submission_format(self, df_preds: pd.DataFrame) -> None:
        """Enforces schema, data types, value bounds, and key integrity."""
        # 1. Column existence
        missing_cols = self.REQUIRED_PRED_COLS - set(df_preds.columns)
        if missing_cols:
            raise ValueError(f"Submission missing required columns: {missing_cols}")

        # 2. Null checks
        if df_preds["predicted_sales"].isnull().any():
            raise ValueError("Submission contains null values in 'predicted_sales'")
        if df_preds["sku_id"].isnull().any():
            raise ValueError("Submission contains null values in 'sku_id'")
        if df_preds["horizon_week"].isnull().any():
            raise ValueError("Submission contains null values in 'horizon_week'")

        # 3. Non-negativity check
        if (df_preds["predicted_sales"] < 0).any():
            raise ValueError("Submission contains negative predicted values in 'predicted_sales'")

        # 4. Finite values check
        if np.isinf(df_preds["predicted_sales"]).any():
            raise ValueError("Submission contains infinite values in 'predicted_sales'")

        # 5. Horizon weeks check (must strictly be {1..8})
        unique_weeks = set(df_preds["horizon_week"].astype(int).unique())
        if not unique_weeks.issubset(self.EXPECTED_HORIZON_WEEKS):
            raise ValueError(f"horizon_week must strictly contain values 1 to 8. Found: {unique_weeks}")

        # 6. Duplication check
        dups = df_preds.duplicated(subset=["sku_id", "horizon_week"])
        if dups.any():
            dup_keys = df_preds.loc[dups, ["sku_id", "horizon_week"]].to_dict(orient="records")
            raise ValueError(f"Duplicate (sku_id, horizon_week) keys found: {dup_keys[:5]}")

        # 7. Strict count check if enforced
        if self.strict_row_count:
            if df_preds["sku_id"].nunique() != self.target_sku_count:
                raise ValueError(
                    f"Expected exactly {self.target_sku_count} unique SKUs, got {df_preds['sku_id'].nunique()}"
                )
            expected_rows = self.target_sku_count * 8
            if len(df_preds) != expected_rows:
                raise ValueError(f"Expected exactly {expected_rows} rows, got {len(df_preds)}")

        # 8. Interval sanity checks if intervals are present
        for prefix in ["", "_80", "_90"]:
            low_col = f"lower_bound{prefix}"
            up_col = f"upper_bound{prefix}"
            if low_col in df_preds.columns and up_col in df_preds.columns:
                if (df_preds[low_col] < 0).any():
                    raise ValueError(f"Negative values detected in interval lower bound: {low_col}")
                if (df_preds[low_col] > df_preds[up_col] + 1e-5).any():
                    raise ValueError(f"Lower bound exceeds upper bound in {low_col} vs {up_col}")

    def evaluate(
        self,
        df_predictions: pd.DataFrame,
        df_ground_truth: pd.DataFrame,
        df_metadata: pd.DataFrame | None = None,
    ) -> OfficialEvaluationReport:
        """Executes full evaluation suite against ground truth."""
        self.validate_submission_format(df_predictions)

        missing_truth = self.REQUIRED_TRUTH_COLS - set(df_ground_truth.columns)
        if missing_truth:
            raise ValueError(f"Ground truth missing required columns: {missing_truth}")

        # Strip actual_sales from predictions if present to avoid collision with truth
        df_preds_clean = df_predictions.drop(columns=["actual_sales"], errors="ignore")

        merged = pd.merge(
            df_preds_clean,
            df_ground_truth,
            on=["sku_id", "horizon_week"],
            how="inner",
        )
        if merged.empty:
            raise ValueError("No matching (sku_id, horizon_week) keys found between predictions and truth.")

        # Ensure category metadata is present
        if "category" in merged.columns:
            merged["category"] = merged["category"].fillna("Unknown")
        elif df_metadata is not None and "category" in df_metadata.columns:
            meta_subset = df_metadata[["sku_id", "category"]].drop_duplicates(subset=["sku_id"])
            merged = pd.merge(merged, meta_subset, on="sku_id", how="left")
            merged["category"] = merged["category"].fillna("Unknown")
        else:
            merged["category"] = "Global"

        y_true = merged["actual_sales"].to_numpy()
        y_pred = merged["predicted_sales"].to_numpy()

        # Primary and secondary point forecast metrics
        total_wape = wape(y_true, y_pred)
        total_rmse = rmse(y_true, y_pred)
        total_mae = mae(y_true, y_pred)
        total_bias = forecast_bias_pct(y_true, y_pred)

        # Per-horizon week WAPE
        weekly_wape_map: dict[int, float] = {}
        for w, w_df in merged.groupby("horizon_week"):
            weekly_wape_map[int(w)] = round(wape(w_df["actual_sales"], w_df["predicted_sales"]), 6)

        # Cumulative 8-week SKU-level metrics
        sku_cum = (
            merged.groupby("sku_id")[["actual_sales", "predicted_sales"]]
            .sum()
            .reset_index()
        )
        cum_wape = wape(sku_cum["actual_sales"], sku_cum["predicted_sales"])
        cum_rmse = rmse(sku_cum["actual_sales"], sku_cum["predicted_sales"])
        cum_mae = mae(sku_cum["actual_sales"], sku_cum["predicted_sales"])
        cum_bias = forecast_bias_pct(sku_cum["actual_sales"], sku_cum["predicted_sales"])

        # Category-level metrics
        category_wape_map: dict[str, float] = {}
        for cat, cat_df in merged.groupby("category"):
            category_wape_map[str(cat)] = round(wape(cat_df["actual_sales"], cat_df["predicted_sales"]), 6)
        cat_stability_std = float(np.std(list(category_wape_map.values())))

        # Interval evaluation if bounds are provided
        interval_eval_results: dict[str, Any] = {}
        for conf_label, conf_level in [("80", 0.80), ("90", 0.90)]:
            low_col = f"lower_bound_{conf_label}" if f"lower_bound_{conf_label}" in merged.columns else "lower_bound"
            up_col = f"upper_bound_{conf_label}" if f"upper_bound_{conf_label}" in merged.columns else "upper_bound"

            if low_col in merged.columns and up_col in merged.columns:
                lb = merged[low_col].to_numpy()
                ub = merged[up_col].to_numpy()
                alpha = round(1.0 - conf_level, 4)

                cov = empirical_coverage(y_true, lb, ub)
                width = mean_interval_width(lb, ub)
                w_score = winkler_score(y_true, lb, ub, alpha=alpha)

                # Horizon week breakdown of coverage
                weekly_cov = {}
                for w, w_df in merged.groupby("horizon_week"):
                    weekly_cov[int(w)] = round(
                        empirical_coverage(w_df["actual_sales"], w_df[low_col], w_df[up_col]), 4
                    )

                # Category breakdown of coverage
                cat_cov = {}
                for cat, cat_df in merged.groupby("category"):
                    cat_cov[str(cat)] = round(
                        empirical_coverage(cat_df["actual_sales"], cat_df[low_col], cat_df[up_col]), 4
                    )

                interval_eval_results[f"coverage_{conf_label}"] = {
                    "nominal_confidence": conf_level,
                    "empirical_coverage": round(cov, 4),
                    "mean_width": round(width, 2),
                    "winkler_score": round(w_score, 2),
                    "coverage_by_week": weekly_cov,
                    "coverage_by_category": cat_cov,
                }

        # Check for dedicated cumulative interval evaluation
        for conf_label, conf_level in [("80", 0.80), ("90", 0.90)]:
            cum_low_col = f"cumul_lower_{conf_label}"
            cum_up_col = f"cumul_upper_{conf_label}"
            if cum_low_col in merged.columns and cum_up_col in merged.columns:
                sku_cum_int = merged.groupby("sku_id").agg({
                    "actual_sales": "sum",
                    cum_low_col: "first",
                    cum_up_col: "first",
                }).reset_index()
                c_lb = sku_cum_int[cum_low_col].to_numpy()
                c_ub = sku_cum_int[cum_up_col].to_numpy()
                c_yt = sku_cum_int["actual_sales"].to_numpy()
                alpha = round(1.0 - conf_level, 4)

                interval_eval_results[f"cumulative_coverage_{conf_label}"] = {
                    "nominal_confidence": conf_level,
                    "empirical_coverage": round(empirical_coverage(c_yt, c_lb, c_ub), 4),
                    "mean_width": round(mean_interval_width(c_lb, c_ub), 2),
                    "winkler_score": round(winkler_score(c_yt, c_lb, c_ub, alpha=alpha), 2),
                }

        return OfficialEvaluationReport(
            evaluation_timestamp=datetime.now(UTC).isoformat(),
            total_skus=int(merged["sku_id"].nunique()),
            total_horizon_points=len(merged),
            overall_wape=round(total_wape, 6),
            overall_rmse=round(total_rmse, 4),
            overall_mae=round(total_mae, 4),
            overall_bias_pct=round(total_bias, 4),
            weekly_wape=weekly_wape_map,
            cumulative_8w_wape=round(cum_wape, 6),
            cumulative_8w_rmse=round(cum_rmse, 4),
            cumulative_8w_mae=round(cum_mae, 4),
            cumulative_8w_bias_pct=round(cum_bias, 4),
            category_wape=category_wape_map,
            category_stability_std=round(cat_stability_std, 4),
            interval_evaluation=interval_eval_results,
            validation_status="PASSED",
            notes=[
                "Zero denominators handled per specification: returns 0.0 if both sum of actuals and sum of errors are zero.",
                "Non-negativity strictly validated across all point forecasts and prediction interval lower bounds.",
            ],
        )
