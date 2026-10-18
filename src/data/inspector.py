"""Automated data schema and quality inspection engine."""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from src.core.logging import logger


@dataclass
class ColumnAudit:
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_percentage: float
    distinct_count: int
    sample_values: list[Any]
    heuristic_tag: str = "general_attribute"


@dataclass
class FileAuditReport:
    file_path: str
    file_name: str
    file_format: str
    file_size_mb: float
    row_count: int
    column_count: int
    duplicate_rows: int
    columns: list[ColumnAudit] = field(default_factory=list)
    heuristic_findings: dict[str, Any] = field(default_factory=dict)


@dataclass
class DirectoryAuditReport:
    directory_path: str
    total_files_scanned: int
    files_audited: list[FileAuditReport] = field(default_factory=list)
    summary_findings: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)


class DataInspector:
    """Discovers, reads, and audits raw retail forecasting datasets."""

    SUPPORTED_EXTENSIONS = {".csv", ".parquet", ".xlsx", ".json"}

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)

    def classify_column_heuristic(self, col_name: str, series: pd.Series) -> str:
        """Determines probable role of a column using heuristic pattern matching."""
        lower = col_name.lower()
        dtype_str = str(series.dtype).lower()

        if any(k in lower for k in ["sku", "product_id", "item_id", "material_num"]):
            return "sku_identifier"
        if any(k in lower for k in ["holiday", "promo", "event", "calendar"]):
            return "holiday_or_event"
        if any(k in lower for k in ["sales", "demand", "units_sold", "qty_sold", "quantity_sold"]) or (
            any(k in lower for k in ["units", "quantity", "qty", "volume"])
            and ("int" in dtype_str or "float" in dtype_str)
        ):
            return "sales_target"
        if any(k in lower for k in ["date", "week", "year", "time", "day", "period", "timestamp"]):
            return "temporal_dimension"
        if any(k in lower for k in ["cluster", "store", "shop", "channel", "region"]):
            return "store_or_cluster"
        if any(k in lower for k in ["price", "cost", "msrp", "margin"]):
            return "financial_attribute"
        if any(k in lower for k in ["stock", "inventory", "on_hand", "days_in_stock"]):
            return "inventory_or_stockout"
        if any(k in lower for k in ["category", "dept", "department", "brand", "class", "group"]):
            return "category_attribute"

        if "int" in dtype_str or "float" in dtype_str:
            return "numerical_feature"
        return "categorical_feature"

    def audit_dataframe(self, df: pd.DataFrame, file_path: Path) -> FileAuditReport:
        """Performs deep schema and distribution audit on an in-memory DataFrame."""
        file_size_mb = (
            file_path.stat().st_size / (1024 * 1024) if file_path.exists() else 0.0
        )
        row_count = len(df)
        col_count = len(df.columns)
        duplicate_rows = int(df.duplicated().sum())

        col_audits: list[ColumnAudit] = []
        heuristic_tags: dict[str, list[str]] = {}

        for col in df.columns:
            s = df[col]
            nulls = int(s.isnull().sum())
            non_nulls = row_count - nulls
            null_pct = round((nulls / row_count) * 100.0, 2) if row_count > 0 else 0.0
            distincts = int(s.nunique(dropna=True))

            # Sample 3 representative non-null values
            non_null_samples = s.dropna().head(3).tolist()
            # Convert non-serializable objects (timestamps, etc.)
            clean_samples = [
                str(val) if isinstance(val, (pd.Timestamp, np.generic)) else val
                for val in non_null_samples
            ]

            tag = self.classify_column_heuristic(str(col), s)
            heuristic_tags.setdefault(tag, []).append(str(col))

            col_audits.append(
                ColumnAudit(
                    name=str(col),
                    dtype=str(s.dtype),
                    non_null_count=non_nulls,
                    null_count=nulls,
                    null_percentage=null_pct,
                    distinct_count=distincts,
                    sample_values=clean_samples,
                    heuristic_tag=tag,
                )
            )

        heuristic_findings: dict[str, Any] = {
            "tagged_columns": heuristic_tags,
            "has_sku_column": "sku_identifier" in heuristic_tags,
            "has_target_column": "sales_target" in heuristic_tags,
            "has_temporal_column": "temporal_dimension" in heuristic_tags,
            "has_cluster_column": "store_or_cluster" in heuristic_tags,
        }

        # Analyze zero sales vs null sales if target column found
        target_cols = heuristic_tags.get("sales_target", [])
        if target_cols:
            for t_col in target_cols:
                series = pd.to_numeric(df[t_col], errors="coerce")
                zero_count = int((series == 0).sum())
                negative_count = int((series < 0).sum())
                heuristic_findings[f"{t_col}_zero_count"] = zero_count
                heuristic_findings[f"{t_col}_negative_count"] = negative_count

        return FileAuditReport(
            file_path=str(file_path.resolve()),
            file_name=file_path.name,
            file_format=file_path.suffix.lower(),
            file_size_mb=round(file_size_mb, 4),
            row_count=row_count,
            column_count=col_count,
            duplicate_rows=duplicate_rows,
            columns=col_audits,
            heuristic_findings=heuristic_findings,
        )

    def load_file_into_df(self, file_path: Path) -> pd.DataFrame:
        """Reads file based on extension without assuming schema."""
        ext = file_path.suffix.lower()
        if ext == ".csv":
            return pd.read_csv(file_path, low_memory=False)
        elif ext == ".parquet":
            return pd.read_parquet(file_path)
        elif ext == ".xlsx":
            return pd.read_excel(file_path)
        elif ext == ".json":
            return pd.read_json(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    def run_directory_audit(self) -> DirectoryAuditReport:
        """Audits all candidate files within target directory."""
        if not self.data_dir.exists():
            return DirectoryAuditReport(
                directory_path=str(self.data_dir),
                total_files_scanned=0,
                blockers=[f"Target directory {self.data_dir} does not exist."],
            )

        candidate_files: list[Path] = []
        for root, _, files in os.walk(self.data_dir):
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    candidate_files.append(p)

        if not candidate_files:
            return DirectoryAuditReport(
                directory_path=str(self.data_dir),
                total_files_scanned=0,
                blockers=[
                    f"No valid dataset files (.csv, .parquet, .xlsx, .json) found in {self.data_dir}."
                ],
            )

        audited_files: list[FileAuditReport] = []
        for file_path in candidate_files:
            logger.info("Auditing file: %s", file_path)
            try:
                df = self.load_file_into_df(file_path)
                report = self.audit_dataframe(df, file_path)
                audited_files.append(report)
            except Exception as e:
                logger.error("Failed to parse %s: %s", file_path, e)
                audited_files.append(
                    FileAuditReport(
                        file_path=str(file_path.resolve()),
                        file_name=file_path.name,
                        file_format=file_path.suffix.lower(),
                        file_size_mb=round(file_path.stat().st_size / (1024 * 1024), 4),
                        row_count=0,
                        column_count=0,
                        duplicate_rows=0,
                        heuristic_findings={"error": str(e)},
                    )
                )

        return DirectoryAuditReport(
            directory_path=str(self.data_dir),
            total_files_scanned=len(audited_files),
            files_audited=audited_files,
            summary_findings={
                "total_files": len(audited_files),
                "total_rows": sum(f.row_count for f in audited_files),
            },
        )
