"""Forecasting API routes for cold-start SKUs."""

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/forecast", tags=["Forecasting"])


class WeeklyPrediction(BaseModel):
    horizon_week: int = Field(..., ge=1, le=8, description="Horizon week index 1-8")
    predicted_sales: float = Field(..., ge=0.0, description="Median expected demand")
    p10_sales: float = Field(..., ge=0.0, description="10th percentile conservative bound")
    p90_sales: float = Field(..., ge=0.0, description="90th percentile upside bound")


class SKUForecastRequest(BaseModel):
    sku_id: str = Field(..., description="Unique SKU Identifier")
    product_name: str | None = Field(default=None, description="Product Name")
    category_l1: str = Field(..., description="Department or Level 1 Category")
    category_l2: str | None = Field(default=None, description="Level 2 Sub-category")
    brand: str | None = Field(default=None, description="Brand name")
    base_price: float = Field(..., gt=0.0, description="Initial introduction price")
    unit_cost: float | None = Field(default=None, gt=0.0, description="Cost of goods sold")


class SKUForecastResponse(BaseModel):
    sku_id: str
    horizon_weeks: list[WeeklyPrediction]
    total_projected_volume: float
    model_version: str = "v0.1.0-coldstart-baseline"
    status: str = "READY"


@router.post("/predict", response_model=SKUForecastResponse)
async def generate_coldstart_forecast(payload: SKUForecastRequest) -> SKUForecastResponse:
    """Predicts weekly sales for the first 8 weeks of a new SKU."""
    # Note: Phase 1 provides interface specification and schema contract.
    # Model inference integration occurs in subsequent modeling phase upon data ingestion.
    raise HTTPException(
        status_code=503,
        detail="Model engine currently uncalibrated. Raw training data ingestion pending (BLK-001).",
    )
