"""Validation harness benchmarking baseline and analogue models on held-out historical launches."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from src.core.logging import logger
from src.evaluation.evaluator import ColdStartEvaluator, EvaluationReport
from src.models.analogue import AnalogueForecaster, AttributeSimilarityEngine
from src.models.baseline import LaunchCurveBaseline


@dataclass
class ModelBenchmarkResult:
    model_name: str
    overall_wape: float
    overall_rmse: float
    overall_mae: float
    overall_bias_pct: float
    weekly_wape: dict[int, float]
    sample_sku_count: int
    eval_points: int


@dataclass
class Phase3BenchmarkReport:
    timestamp: str
    total_historical_skus: int
    train_donor_skus: int
    held_out_validation_skus: int
    split_ratio: str
    models: list[ModelBenchmarkResult] = field(default_factory=list)
    observations_and_limitations: list[str] = field(default_factory=list)


class ColdStartValidator:
    """Rigorous offline validation on historical launches."""

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.evaluator = ColdStartEvaluator()

    def create_held_out_split(
        self,
        df_mature_attr: pd.DataFrame,
        validation_ratio: float = 0.1667,  # ~200 out of 1,200 SKUs
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Deterministically splits SKUs into donor pool and held-out validation cohort."""
        np.random.seed(self.random_seed)
        unique_skus = df_mature_attr["sku_id"].unique()
        n_val = int(len(unique_skus) * validation_ratio)

        val_skus = set(np.random.choice(unique_skus, size=n_val, replace=False))
        train_skus = set(unique_skus) - val_skus

        df_train = df_mature_attr[df_mature_attr["sku_id"].isin(train_skus)].copy()
        df_val = df_mature_attr[df_mature_attr["sku_id"].isin(val_skus)].copy()

        logger.info(
            "Held-out SKU split created: %d train donor SKUs, %d validation SKUs.",
            len(train_skus),
            len(val_skus),
        )
        return df_train, df_val

    def evaluate_model_predictions(
        self,
        model_name: str,
        df_predictions: pd.DataFrame,
        df_ground_truth: pd.DataFrame,
    ) -> ModelBenchmarkResult:
        """Evaluates predictions against ground truth using standard ColdStartEvaluator."""
        report: EvaluationReport = self.evaluator.evaluate(df_predictions, df_ground_truth)
        return ModelBenchmarkResult(
            model_name=model_name,
            overall_wape=report.overall_wape,
            overall_rmse=report.overall_rmse,
            overall_mae=report.overall_mae,
            overall_bias_pct=report.overall_bias_pct,
            weekly_wape=report.weekly_wape,
            sample_sku_count=report.total_skus,
            eval_points=report.total_eval_points,
        )

    def run_benchmark(
        self,
        df_mature_attr: pd.DataFrame,
        df_mature_sales: pd.DataFrame,
        df_train_features: pd.DataFrame,
    ) -> Phase3BenchmarkReport:
        """Runs comparative offline benchmark on held-out historical launches."""
        # 1. Create held-out split
        df_donor_attr, df_val_attr = self.create_held_out_split(df_mature_attr)
        donor_sku_set = set(df_donor_attr["sku_id"])
        val_sku_set = set(df_val_attr["sku_id"])

        # 2. Extract donor sales & validation ground truth
        df_donor_features = df_train_features[df_train_features["sku_id"].isin(donor_sku_set)].copy()
        df_donor_sales = df_mature_sales[df_mature_sales["sku_id"].isin(donor_sku_set)].copy()

        # Build ground truth enterprise sales per validation SKU per week
        val_sales = df_train_features[df_train_features["sku_id"].isin(val_sku_set)]
        ground_truth = (
            val_sales.groupby(["sku_id", "launch_week_age"])["units_sold"]
            .sum()
            .reset_index()
            .rename(columns={"launch_week_age": "horizon_week", "units_sold": "actual_sales"})
        )

        results: list[ModelBenchmarkResult] = []

        # ----------------------------------------------------------------------
        # Model 1: Global Empirical Median Curve
        # ----------------------------------------------------------------------
        logger.info("Evaluating Model 1: Global Empirical Baseline...")
        global_baseline = LaunchCurveBaseline(min_donor_skus=999999, aggregation_method="median")
        global_baseline.fit(df_donor_features)
        pred_global = global_baseline.predict_dataframe(df_val_attr)
        res_global = self.evaluate_model_predictions("Global Empirical Median", pred_global, ground_truth)
        results.append(res_global)

        # ----------------------------------------------------------------------
        # Model 2: Hierarchical Category / Subcategory Baseline (Median)
        # ----------------------------------------------------------------------
        logger.info("Evaluating Model 2: Hierarchical Category/Subcategory Baseline (Median)...")
        cat_baseline_med = LaunchCurveBaseline(min_donor_skus=5, aggregation_method="median")
        cat_baseline_med.fit(df_donor_features)
        pred_cat_med = cat_baseline_med.predict_dataframe(df_val_attr)
        res_cat_med = self.evaluate_model_predictions("Category/Subcategory Baseline (Median)", pred_cat_med, ground_truth)
        results.append(res_cat_med)

        # ----------------------------------------------------------------------
        # Model 3: Hierarchical Category / Subcategory Baseline (Mean)
        # ----------------------------------------------------------------------
        logger.info("Evaluating Model 3: Hierarchical Category/Subcategory Baseline (Mean)...")
        cat_baseline_mean = LaunchCurveBaseline(min_donor_skus=5, aggregation_method="mean")
        cat_baseline_mean.fit(df_donor_features)
        pred_cat_mean = cat_baseline_mean.predict_dataframe(df_val_attr)
        res_cat_mean = self.evaluate_model_predictions("Category/Subcategory Baseline (Mean)", pred_cat_mean, ground_truth)
        results.append(res_cat_mean)

        # ----------------------------------------------------------------------
        # Model 4: Top-5 Analogue Retrieval Forecaster
        # ----------------------------------------------------------------------
        logger.info("Evaluating Model 4: Top-5 Analogue Retrieval Forecaster...")
        sim_engine = AttributeSimilarityEngine()
        sim_engine.fit_candidates(df_donor_attr, df_donor_sales)
        analogue_forecaster = AnalogueForecaster(sim_engine, k=5, temperature_power=2.0)
        pred_analogue, _ = analogue_forecaster.forecast_dataframe(df_val_attr, exclude_self=True)
        res_analogue = self.evaluate_model_predictions("Top-5 Analogue Retrieval (Power-2 Weighted)", pred_analogue, ground_truth)
        results.append(res_analogue)

        limitations = [
            "Category baselines predict static profiles that ignore granular product attributes (price, material, colour).",
            "Analogue retrieval provides adaptive attribute-specific forecasts, but variance is sensitive to the donor pool density.",
            "Both models lack cross-sectional gradient boosting or complex interactions, which will be addressed in Phase 4.",
            "Evaluation was conducted on enterprise-aggregated weekly totals; store-level allocation requires spatial disaggregation.",
        ]

        val_ratio_pct = (len(val_sku_set) / max(1, len(df_mature_attr))) * 100.0
        report = Phase3BenchmarkReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_historical_skus=len(df_mature_attr),
            train_donor_skus=len(donor_sku_set),
            held_out_validation_skus=len(val_sku_set),
            split_ratio=f"{len(donor_sku_set)} train / {len(val_sku_set)} held-out (~{val_ratio_pct:.1f}%)",
            models=results,
            observations_and_limitations=limitations,
        )

        return report

    def save_markdown_report(self, report: Phase3BenchmarkReport, output_path: Path) -> None:
        """Formats and saves benchmark report in Markdown."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# PHASE 3 BENCHMARK REPORT — BASELINES & ANALOGUE RETRIEVAL",
            "",
            f"**Evaluation Date:** `{report.timestamp}`  ",
            f"**Validation Cohort:** `{report.held_out_validation_skus}` held-out SKUs ({report.split_ratio})  ",
            f"**Evaluation Target:** Enterprise sales across Launch Weeks $W_1$ through $W_8$  ",
            "",
            "## 1. Model Comparison Summary (Offline Held-Out Launches)",
            "",
            "| Model Architecture | WAPE (Primary) | RMSE | MAE | Bias % | Evaluated SKUs | Total Eval Points |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for m in report.models:
            lines.append(
                f"| **{m.model_name}** | **`{m.overall_wape:.4f}`** | `{m.overall_rmse:.2f}` | `{m.overall_mae:.2f}` | `{m.overall_bias_pct:+.2f}%` | `{m.sample_sku_count}` | `{m.eval_points:,}` |"
            )

        lines.extend([
            "",
            "## 2. Multi-Horizon WAPE Breakdown ($W_1$ to $W_8$)",
            "",
            "| Model | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])

        for m in report.models:
            w_vals = " | ".join([f"`{m.weekly_wape.get(w, 0.0):.3f}`" for w in range(1, 9)])
            lines.append(f"| {m.model_name} | {w_vals} |")

        lines.extend([
            "",
            "## 3. Methodological Observations & Limitations",
        ])
        for obs in report.observations_and_limitations:
            lines.append(f"- {obs}")

        lines.append("")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
