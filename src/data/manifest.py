"""Versioned data manifest generation for pipeline lineage and audit reproducibility."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
import pandas as pd


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    if not file_path.exists():
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit_hash() -> str:
    """Retrieves current Git commit SHA if in a repository."""
    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return output.decode("utf-8").strip()
    except Exception:
        return "UNKNOWN_COMMIT"


@dataclass
class FileManifestItem:
    file_name: str
    relative_path: str
    sha256_hash: str
    size_bytes: int
    row_count: int
    column_count: int
    columns: list[str] = field(default_factory=list)


@dataclass
class DataManifest:
    manifest_version: str = "2.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    git_commit: str = field(default_factory=get_git_commit_hash)
    python_version: str = field(default_factory=lambda: sys.version)
    random_seed: int = 42
    source_raw_files: list[FileManifestItem] = field(default_factory=list)
    interim_files: list[FileManifestItem] = field(default_factory=list)
    processed_files: list[FileManifestItem] = field(default_factory=list)
    feature_schema: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ManifestGenerator:
    """Compiles and registers versioned dataset manifests."""

    def create_manifest_item(self, file_path: Path, df: pd.DataFrame | None = None) -> FileManifestItem:
        """Inspects file and returns structured manifest item."""
        sha = compute_file_sha256(file_path)
        size = file_path.stat().st_size if file_path.exists() else 0
        rows = len(df) if df is not None else 0
        cols = list(df.columns) if df is not None else []

        return FileManifestItem(
            file_name=file_path.name,
            relative_path=str(file_path),
            sha256_hash=sha,
            size_bytes=size,
            row_count=rows,
            column_count=len(cols),
            columns=cols,
        )

    def save_manifest(self, manifest: DataManifest, target_path: Path) -> None:
        """Serializes manifest to JSON."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(asdict(manifest), f, indent=2)
