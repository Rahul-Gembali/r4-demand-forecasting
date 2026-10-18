"""Cold-start demand forecast evaluation runner."""

from typing import Any
import pandas as pd
from pydantic import BaseModel, Field

from src.evaluation.metrics import (
    forecast_bias_pct,
    mae,
    pinball_loss,
    rmse,
    wape,
)


class EvaluationReport(BaseModel):
    """Structured report returned by the evaluation engine."""

    total_skus: int = Field(..., description="Number of unique evaluated SKUs")
    total_eval_points: int = Field(..., description="Total SKU-week prediction pairs evaluated")
    overall_wape: float = Field(..., description="Primary Weighted Absolute Percentage Error")
    overall_rmse: float = Field(..., description="Root Mean Squared Error")
    overall_mae: float = Field(..., description="Mean Absolute Error")
    overall_bias_pct: float = Field(..., description="Forecast Bias Percentage")
    weekly_wape: dict[int, float] = Field(..., description="WAPE broken down by horizon week 1-8")
    status: str = Field(default="SUCCESS", description="Evaluation execution status")


class ColdStartEvaluator:
    """Evaluates cold-start demand forecasts against true realized sales."""

    REQUIRED_PRED_COLS = {"sku_id", "horizon_week", "predicted_sales"}
    REQUIRED_TRUTH_COLS = {"sku_id", "horizon_week", "actual_sales"}

    def validate_predictions(self, df: pd.DataFrame) -> None:
        """Validates schema, nullability, and bounds for forecast submissions."""
        missing = self.REQUIRED_PRED_COLS - set(df.columns)
        if missing:
            raise ValueError(f"Submission dataframe missing required columns: {missing}")

        if df["predicted_sales"].isnull().any():
            raise ValueError("Submission contains null values in 'predicted_sales'")

        if (df["predicted_sales"] < 0).any():
            raise ValueError("Submission contains negative predicted values")

        invalid_weeks = df[~df["horizon_week"].isin(range(1, 9))]
        if not invalid_weeks.empty:
            raise ValueError("horizon_week must strictly contain values between 1 and 8")

        dups = df.duplicated(subset=["sku_id", "horizon_week"])
        if dups.any():
            raise ValueError("Submission contains duplicate (sku_id, horizon_week) keys")

    def evaluate(
        self,
        predictions_df: pd.DataFrame,
        ground_truth_df: pd.DataFrame,
    ) -> EvaluationReport:
        """Runs full evaluation comparing predictions with ground truth."""
        self.validate_predictions(predictions_df)

        missing_truth = self.REQUIRED_TRUTH_COLS - set(ground_truth_df.columns)
        if missing_truth:
            raise ValueError(f"Ground truth dataframe missing required columns: {missing_truth}")

        merged = pd.merge(
            predictions_df,
            ground_truth_df,
            on=["sku_id", "horizon_week"],
            how="inner",
        )

        if merged.empty:
            raise ValueError("No matching (sku_id, horizon_week) pairs between predictions and truth")

        y_true = merged["actual_sales"].to_numpy()
        y_pred = merged["predicted_sales"].to_numpy()

        overall_wape_val = wape(y_true, y_pred)
        overall_rmse_val = rmse(y_true, y_pred)
        overall_mae_val = mae(y_true, y_pred)
        overall_bias_val = forecast_bias_pct(y_true, y_pred)

        # Weekly WAPE breakdown
        weekly_wape_dict: dict[int, float] = {}
        for week_idx, group in merged.groupby("horizon_week"):
            w_true = group["actual_sales"].to_numpy()
            w_pred = group["predicted_sales"].to_numpy()
            weekly_wape_dict[int(week_idx)] = wape(w_true, w_pred)

        return EvaluationReport(
            total_skus=int(merged["sku_id"].nunique()),
            total_eval_points=len(merged),
            overall_wape=round(overall_wape_val, 6),
            overall_rmse=round(overall_rmse_val, 4),
            overall_mae=round(overall_mae_val, 4),
            overall_bias_pct=round(overall_bias_val, 4),
            weekly_wape={k: round(v, 6) for k, v in weekly_wape_dict.items()},
            status="SUCCESS",
        )
