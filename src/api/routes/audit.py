"""Data discovery and audit status endpoints."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from src.core.config import settings
from src.data.inspector import DataInspector

router = APIRouter(prefix="/audit", tags=["Data Audit"])


@router.get("/status")
async def get_audit_status() -> dict[str, Any]:
    """Returns the latest data audit summary and blocker status."""
    audit_file = Path("docs/data_audit_results.json")
    if audit_file.exists():
        with open(audit_file, encoding="utf-8") as f:
            return json.load(f)

    # If file doesn't exist yet, run inspection on the fly
    inspector = DataInspector(settings.data_raw_dir)
    report = inspector.run_directory_audit()
    return asdict(report)
