"""Health check and system status endpoints."""

from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/health", tags=["Health"])


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Service health status")
    version: str = Field(default="0.1.0", description="Application version")
    service: str = Field(
        default="r4-new-product-demand-forecasting", description="Service identifier"
    )


@router.get("", response_model=HealthResponse)
async def check_health() -> HealthResponse:
    """Liveness probe returning operational state."""
    return HealthResponse()
