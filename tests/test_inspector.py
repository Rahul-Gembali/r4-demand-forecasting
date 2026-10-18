"""Unit tests for DataInspector schema discovery and anomaly auditing."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.data.inspector import DataInspector


def test_empty_directory_handling(tmp_path: Path):
    empty_dir = tmp_path / "empty_raw"
    empty_dir.mkdir()

    inspector = DataInspector(empty_dir)
    report = inspector.run_directory_audit()

    assert report.total_files_scanned == 0
    assert len(report.blockers) > 0
    assert "No valid dataset files" in report.blockers[0]


def test_nonexistent_directory_handling(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist"

    inspector = DataInspector(non_existent)
    report = inspector.run_directory_audit()

    assert report.total_files_scanned == 0
    assert len(report.blockers) > 0
    assert "does not exist" in report.blockers[0]


def test_dataframe_audit_heuristics(tmp_path: Path):
    # Construct a representative retail forecasting dataframe
    df = pd.DataFrame({
        "sku_id": ["SKU_001", "SKU_002", "SKU_003", "SKU_001"],
        "week_start_date": ["2026-01-05", "2026-01-05", "2026-01-05", "2026-01-12"],
        "store_cluster_id": ["Cluster_A", "Cluster_B", "Cluster_A", "Cluster_A"],
        "weekly_sales_units": [120.0, 0.0, 45.0, 110.0],
        "base_price": [19.99, 29.99, 14.99, 19.99],
        "is_holiday_week": [0, 0, 0, 1],
    })

    file_path = tmp_path / "sample_sales.csv"
    df.to_csv(file_path, index=False)

    inspector = DataInspector(tmp_path)
    report = inspector.audit_dataframe(df, file_path)

    assert report.row_count == 4
    assert report.column_count == 6
    assert report.duplicate_rows == 0

    findings = report.heuristic_findings
    assert findings["has_sku_column"] is True
    assert findings["has_target_column"] is True
    assert findings["has_temporal_column"] is True
    assert findings["has_cluster_column"] is True
    assert findings["weekly_sales_units_zero_count"] == 1
    assert findings["weekly_sales_units_negative_count"] == 0

    # Verify column audit entries
    col_map = {c.name: c for c in report.columns}
    assert col_map["sku_id"].heuristic_tag == "sku_identifier"
    assert col_map["weekly_sales_units"].heuristic_tag == "sales_target"
    assert col_map["week_start_date"].heuristic_tag == "temporal_dimension"
    assert col_map["store_cluster_id"].heuristic_tag == "store_or_cluster"
    assert col_map["base_price"].heuristic_tag == "financial_attribute"
    assert col_map["is_holiday_week"].heuristic_tag == "holiday_or_event"


def test_null_value_and_duplicate_detection(tmp_path: Path):
    df_with_issues = pd.DataFrame({
        "item_id": ["A", "B", "A", None],
        "sales_qty": [10.0, None, 10.0, 5.0],
    })

    file_path = tmp_path / "issues.csv"
    df_with_issues.to_csv(file_path, index=False)

    inspector = DataInspector(tmp_path)
    report = inspector.audit_dataframe(df_with_issues, file_path)

    assert report.row_count == 4
    # Row 0 and Row 2 are identical duplicates
    assert report.duplicate_rows == 1

    col_map = {c.name: c for c in report.columns}
    assert col_map["item_id"].null_count == 1
    assert col_map["item_id"].null_percentage == 25.0
    assert col_map["sales_qty"].null_count == 1
