"""Secure Data Ingestion and Import Endpoints."""

import hashlib
import os
import re
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import AuthenticatedUser, require_operator
from src.api.schemas import DataImportSummary
from src.core.config import settings
from src.core.logging import get_logger
from src.db.repository import ForecastRepository
from src.db.session import get_db_session

logger = get_logger("api_data")
router = APIRouter(prefix="/data", tags=["Data Pipeline & Ingestion"])

ALLOWED_EXTENSIONS = {".csv", ".parquet", ".xlsx"}


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    clean = Path(filename).name
    clean = re.sub(r"[^\w\.\-_]", "_", clean)
    if not clean or clean.startswith("."):
        clean = f"upload_{int(pd.Timestamp.now().timestamp())}.csv"
    return clean


@router.post(
    "/import",
    response_model=DataImportSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Securely Import Product Attributes or Sales Data",
)
async def import_data(
    file: Annotated[UploadFile, File(description="CSV, Parquet, or Excel file to upload")],
    manifest_type: Annotated[str, Form(description="Target dataset identifier")] = "NEW_SKUS",
    is_evaluation_data: Annotated[bool, Form(description="Mark imported items as cold-start candidates")] = True,
    current_user: AuthenticatedUser = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> DataImportSummary:
    """Upload and ingest product attributes or reference records.

    Features:
    - Path traversal prevention and sandboxed destination storage.
    - Extension whitelist and 50MB maximum size restriction.
    - Automatic schema validation and type normalization.
    - Cryptographic SHA256 provenance registration.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    # 1. Extension Verification
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension '{file_ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # 2. Destination Directory & Safe File Path
    settings.data_uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(file.filename)
    dest_path = (settings.data_uploads_dir / safe_name).resolve()

    # Path traversal protection assertion
    if not dest_path.is_relative_to(settings.data_uploads_dir.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security violation: Path traversal detected in upload filename.",
        )

    # 3. Stream File with Size Limiting & SHA256 Calculation
    sha256 = hashlib.sha256()
    total_bytes = 0

    with open(dest_path, "wb") as buffer:
        while chunk := await file.read(65536):
            total_bytes += len(chunk)
            if total_bytes > settings.max_upload_size_bytes:
                buffer.close()
                if dest_path.exists():
                    os.remove(dest_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Upload size exceeds maximum limit of {settings.max_upload_size_bytes // (1024 * 1024)} MB.",
                )
            sha256.update(chunk)
            buffer.write(chunk)

    sha_digest = sha256.hexdigest()

    # 4. Parse Uploaded File
    try:
        if file_ext == ".csv":
            df = pd.read_csv(dest_path)
        elif file_ext == ".parquet":
            df = pd.read_parquet(dest_path)
        else:
            df = pd.read_excel(dest_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse uploaded {file_ext} file: {str(exc)}",
        )

    warnings: list[str] = []
    rows_parsed = len(df)
    skus_upserted = 0

    repo = ForecastRepository(session)

    # 5. Ingest into SKU Catalogue if columns match
    if "sku_id" in df.columns:
        sku_records = []
        for idx, row in df.iterrows():
            sku_id = str(row["sku_id"]).strip()
            if not sku_id or pd.isna(row["sku_id"]):
                warnings.append(f"Row {idx} skipped: missing sku_id.")
                continue

            category = str(row.get("category", "General")).strip()
            subcategory = str(row.get("subcategory", category)).strip()
            product_name = str(row.get("product_name", f"{category} Item {sku_id}")).strip()

            try:
                base_price = float(row.get("base_price", 50.0))
                if base_price <= 0:
                    base_price = 50.0
                    warnings.append(f"SKU {sku_id}: non-positive price adjusted to 50.0.")
            except (ValueError, TypeError):
                base_price = 50.0

            launch_date_val = pd.to_datetime(
                row.get("launch_date", pd.Timestamp.now())
            ).date()

            sku_records.append(
                {
                    "sku_id": sku_id,
                    "product_name": product_name,
                    "category": category,
                    "subcategory": subcategory,
                    "colour": str(row.get("colour", "")) if pd.notna(row.get("colour")) else None,
                    "material": str(row.get("material", "")) if pd.notna(row.get("material")) else None,
                    "base_price": base_price,
                    "brand": str(row.get("brand", "")) if pd.notna(row.get("brand")) else None,
                    "brand_tier": str(row.get("brand_tier", "")) if pd.notna(row.get("brand_tier")) else None,
                    "launch_date": launch_date_val,
                    "has_marketing_support": bool(row.get("has_marketing_support", False)),
                    "is_evaluation_sku": is_evaluation_data,
                }
            )

        if sku_records:
            skus_upserted = await repo.bulk_upsert_skus(sku_records)

    # 6. Record Data Lineage Manifest
    await repo.record_data_manifest(
        {
            "manifest_type": manifest_type,
            "file_identifier": str(dest_path.as_posix()),
            "sha256_checksum": sha_digest,
            "row_count": rows_parsed,
            "schema_snapshot": {
                "columns": df.columns.tolist(),
                "dtypes": {c: str(d) for c, d in df.dtypes.items()},
                "uploaded_by": current_user.name,
            },
        }
    )
    await session.commit()

    logger.info(
        f"Successfully imported {rows_parsed} records ({skus_upserted} SKUs) "
        f"from '{safe_name}' [SHA256: {sha_digest[:8]}...]"
    )

    return DataImportSummary(
        filename=safe_name,
        manifest_type=manifest_type,
        rows_parsed=rows_parsed,
        skus_upserted=skus_upserted,
        sha256_checksum=sha_digest,
        is_evaluation_data=is_evaluation_data,
        warnings=warnings[:10],
    )
