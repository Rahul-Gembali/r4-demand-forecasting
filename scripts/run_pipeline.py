#!/usr/bin/env python3
"""CLI Runner for the End-to-End Data Pipeline.

Executes raw-to-processed pipeline, validates data quality, and outputs manifests.
"""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.logging import logger
from src.data.pipeline import DataPipeline


def main() -> int:
    print("=" * 80)
    print(" R4 DEMAND FORECASTING — PHASE 2 DATA PIPELINE & QUALITY AUDIT")
    print("=" * 80)

    try:
        pipeline = DataPipeline()
        train_df, inference_df, quality_report, manifest = pipeline.run_pipeline()

        print("\nPipeline Execution Successful:")
        print(f"  - Mature Training Records:    {len(train_df):,} rows (Across {train_df['sku_id'].nunique()} SKUs)")
        print(f"  - Target Inference Records:   {len(inference_df):,} rows (Across {inference_df['sku_id'].nunique()} SKUs)")
        print(f"  - Data Quality Status:        {quality_report.overall_status}")
        print(f"  - Target Leakage Check:       {'PASSED (ZERO LEAKAGE)' if quality_report.leakage_check_passed else 'FAILED'}")
        print(f"  - Git Lineage Commit:         {manifest.git_commit[:8] if manifest.git_commit else 'N/A'}")
        print(f"  - Manifest Location:          data/processed/data_manifest.json")
        print(f"  - Audit Report Location:      docs/DATA_QUALITY_REPORT.md\n")

        print("Quality Audit Checks Breakdown:")
        for check in quality_report.checks:
            badge = "[PASS]" if check.status == "PASSED" else f"[{check.status}]"
            print(f"  {badge:7s} {check.check_name}: {check.message}")

        print("=" * 80)
        return 0
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        print(f"\n[ERROR] Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
