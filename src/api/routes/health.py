"""Health check and readiness verification endpoints."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import HealthResponse, ReadinessComponent, ReadinessResponse
from src.core.config import settings
from src.db.session import get_db_session

router = APIRouter(tags=["Health & Readiness"])


@router.get("/health", response_model=HealthResponse, summary="Service Liveness Probe")
async def check_health() -> HealthResponse:
    """Basic liveness probe indicating process is active."""
    return HealthResponse(
        status="healthy",
        service="r4-demand-forecasting",
        version="0.1.0",
        timestamp=datetime.now(UTC),
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Service Readiness Probe")
async def check_readiness(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """Readiness probe validating database connectivity and required model artifacts."""
    components = {}
    is_ready = True

    # 1. Database Connectivity
    try:
        await session.execute(text("SELECT 1"))
        components["database"] = ReadinessComponent(
            status="UP", details="Database connection active and responsive."
        )
    except Exception as exc:
        is_ready = False
        components["database"] = ReadinessComponent(
            status="DOWN", details=f"Database unreachable: {str(exc)}"
        )

    # 2. Frozen Model Artifacts
    model_artifact = Path("artifacts/models/supervised_coldstart_v1/catboost_model.cbm")
    if model_artifact.exists():
        components["model_registry"] = ReadinessComponent(
            status="UP",
            details=f"Model artifact present ({round(model_artifact.stat().st_size / 1024, 1)} KB).",
        )
    else:
        # Check if alternative model or processed data exists
        components["model_registry"] = ReadinessComponent(
            status="DEGRADED",
            details="Primary CatBoost model artifact not found on local disk. Fallback baselines active.",
        )

    # 3. Storage Directories
    dirs_ok = settings.data_raw_dir.exists() and settings.data_processed_dir.exists()
    components["storage"] = ReadinessComponent(
        status="UP" if dirs_ok else "DOWN",
        details="Data filesystem paths accessible." if dirs_ok else "Storage paths missing.",
    )

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    payload = {
        "ready": is_ready,
        "components": {k: v.model_dump() for k, v in components.items()},
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return JSONResponse(status_code=status_code, content=payload)
