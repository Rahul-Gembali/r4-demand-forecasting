#!/usr/bin/env python3
"""Phase 3 Baseline Forecasting and Analogue Retrieval Runner.

1. Benchmarks Category Baselines vs. Analogue Retrieval on held-out historical launches.
2. Generates separate 8-week cold-start forecasts for the 150 target evaluation SKUs.
3. Exports benchmark reports, forecast files, and analogue retrieval audit records.
"""

from dataclasses import asdict
import json
from pathlib import Path
import sys
import pandas as pd

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.logging import logger
from src.models.analogue import AnalogueForecaster, AttributeSimilarityEngine
from src.models.baseline import LaunchCurveBaseline
from src.models.validation import ColdStartValidator


def main() -> int:
    print("=" * 80)
    print(" R4 DEMAND FORECASTING — PHASE 3 BASELINES & ANALOGUE RETRIEVAL")
    print("=" * 80)

    raw_dir = Path("data/raw")
    processed_dir = Path("data/processed")
    docs_dir = Path("docs")

    # 1. Load data
    print("\n1. Loading processed feature store and attributes...")
    df_train_features = pd.read_parquet(processed_dir / "train_features.parquet")
    df_mature_attr = pd.read_csv(raw_dir / "mature_sku_attributes.csv")
    df_mature_sales = pd.read_csv(raw_dir / "historical_sales.csv")
    df_new_attr = pd.read_csv(raw_dir / "new_sku_attributes.csv")

    print(f"   - Mature SKUs in Catalog:     {len(df_mature_attr):,}")
    print(f"   - Historical Sales Records:   {len(df_mature_sales):,}")
    print(f"   - Target Evaluation SKUs:     {len(df_new_attr):,}")

    # 2. Run Comparative Offline Benchmark on Held-Out Historical Launches
    print("\n2. Executing offline benchmark on held-out historical launches (200 SKUs)...")
    validator = ColdStartValidator(random_seed=42)
    benchmark_report = validator.run_benchmark(df_mature_attr, df_mature_sales, df_train_features)

    # Save benchmark reports
    json_path = docs_dir / "phase3_benchmark_results.json"
    md_path = docs_dir / "BASELINE_AND_ANALOGUE_BENCHMARK.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(benchmark_report), f, indent=2)
    validator.save_markdown_report(benchmark_report, md_path)

    print("\nBenchmark Results Summary (Held-Out Cold-Start Launches):")
    print(f"{'Model Architecture':<42} | {'WAPE':<8} | {'RMSE':<8} | {'MAE':<8} | {'Bias %':<8}")
    print("-" * 82)
    for m in benchmark_report.models:
        print(f"{m.model_name:<42} | {m.overall_wape:.4f}   | {m.overall_rmse:<8.2f} | {m.overall_mae:<8.2f} | {m.overall_bias_pct:+.2f}%")

    # 3. Fit Production Models on Full Historical Corpus (1,200 SKUs)
    print("\n3. Training full production baseline & analogue retrieval models on 1,200 SKUs...")
    # Baseline
    cat_baseline = LaunchCurveBaseline(min_donor_skus=5, aggregation_method="median")
    cat_baseline.fit(df_train_features)

    # Analogue Retrieval
    sim_engine = AttributeSimilarityEngine()
    sim_engine.fit_candidates(df_mature_attr, df_mature_sales)
    analogue_forecaster = AnalogueForecaster(sim_engine, k=5, temperature_power=2.0)

    # 4. Generate Separate 8-Week Forecasts for 150 Target Evaluation SKUs
    print("\n4. Generating 8-week cold-start forecasts for the 150 evaluation SKUs...")

    # A. Baseline Forecast
    df_pred_baseline = cat_baseline.predict_dataframe(df_new_attr)
    baseline_out = processed_dir / "forecasts_baseline_150_skus.csv"
    df_pred_baseline.to_csv(baseline_out, index=False)
    print(f"   - Saved Baseline Forecasts:  {baseline_out} ({len(df_pred_baseline)} rows)")

    # B. Analogue Retrieval Forecast
    df_pred_analogue, audit_records = analogue_forecaster.forecast_dataframe(df_new_attr)
    analogue_out = processed_dir / "forecasts_analogue_150_skus.csv"
    df_pred_analogue.to_csv(analogue_out, index=False)
    print(f"   - Saved Analogue Forecasts:  {analogue_out} ({len(df_pred_analogue)} rows)")

    # C. Save Analogue Retrieval Audit Log
    records_out = processed_dir / "analogue_retrieval_records.json"
    with open(records_out, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)
    print(f"   - Saved Analogue Audit Log:  {records_out} ({len(audit_records)} SKU queries)")

    # Inspect fallback breakdown for baseline
    fallback_counts = df_pred_baseline.groupby("fallback_level")["sku_id"].nunique().to_dict()
    print(f"\nBaseline Fallback Distribution across 150 New SKUs: {fallback_counts}")

    print("\n" + "=" * 80)
    print("Phase 3 Execution Completed Successfully.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
