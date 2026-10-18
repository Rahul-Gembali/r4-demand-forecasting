#!/usr/bin/env python3
"""Preliminary Data Discovery and Schema Inspection Script.

Can be rerun repeatedly as new datasets are ingested.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

# Ensure src is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.logging import logger
from src.data.inspector import DataInspector


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and discover schema/quality of raw datasets for R4 Demand Forecasting."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/raw",
        help="Path to directory containing raw dataset files (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/data_audit_results.json",
        help="Path to save JSON audit results (default: docs/data_audit_results.json)",
    )
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
        help="Exit with non-zero code if files are missing or parsing fails.",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_path = Path(args.output)

    print("=" * 80)
    print(" R4 DEMAND FORECASTING — AUTOMATED DATA DISCOVERY & SCHEMA INSPECTION")
    print("=" * 80)
    print(f"Target Directory: {data_dir.resolve()}")
    print(f"Audit Output:     {output_path.resolve()}\n")

    inspector = DataInspector(data_dir)
    report = inspector.run_directory_audit()

    # Save JSON report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)

    # Print summary to console
    print(f"Total Files Scanned: {report.total_files_scanned}")

    if report.blockers:
        print("\n[!] CRITICAL AUDIT FINDINGS / BLOCKERS IDENTIFIED:")
        for blocker in report.blockers:
            print(f"  - {blocker}")
        print("\nAction Required:")
        print(f"  Place raw dataset files (CSV/Parquet) into: {data_dir.resolve()}")
        print("  Then re-run: python scripts/inspect_data.py")
        print("=" * 80)
        return 1 if args.fail_on_blocker else 0

    print("\nAudited Files Detail:")
    for f in report.files_audited:
        print(f"\n[FILE] {f.file_name} ({f.file_format.upper()}, {f.file_size_mb} MB)")
        print(f"       Rows: {f.row_count:,} | Columns: {f.column_count} | Duplicates: {f.duplicate_rows}")
        print("       Heuristic Tags:")
        for tag, cols in f.heuristic_findings.get("tagged_columns", {}).items():
            print(f"         - {tag}: {cols}")

    print("\n" + "=" * 80)
    print(f"Audit report saved successfully to: {output_path}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
