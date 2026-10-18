"""Formal Pydantic and Typed schemas for Raw, Interim, and Processed data."""

from datetime import date
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class LifecycleStage(str, Enum):
    MATURE = "MATURE"
    DISCONTINUED = "DISCONTINUED"
    NEW_LAUNCH = "NEW_LAUNCH"


class PriceBand(str, Enum):
    BUDGET = "Budget"          # < $25
    MID_RANGE = "Mid-Range"    # $25 <= price < $75
    PREMIUM = "Premium"        # $75 <= price < $150
    LUXURY = "Luxury"          # >= $150


class BrandTier(str, Enum):
    TIER_1 = "Tier 1 National"
    TIER_2 = "Tier 2 Regional"
    TIER_3 = "Tier 3 Value"


class ObservationStatus(str, Enum):
    OBSERVED_POSITIVE = "OBSERVED_POSITIVE"
    GENUINE_ZERO = "GENUINE_ZERO"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"


# ==============================================================================
# Raw Ingestion Schemas
# ==============================================================================

class RawProductAttribute(BaseModel):
    """Raw product catalog attribute record."""
    sku_id: str = Field(..., min_length=1, description="Unique SKU identifier")
    product_name: str | None = Field(default=None)
    category: str = Field(..., min_length=1, description="Primary category")
    subcategory: str | None = Field(default=None, description="Sub-category grouping")
    colour: str | None = Field(default=None, description="Primary colour")
    material: str | None = Field(default=None, description="Primary material composition")
    base_price: float = Field(..., gt=0.0, description="Introduction unit price")
    brand: str | None = Field(default=None, description="Brand name")
    brand_tier: str | None = Field(default=None, description="Brand positioning tier")
    launch_date: date = Field(..., description="Commercial introduction date")
    has_marketing_support: bool = Field(default=True, description="Marketing campaign investment flag")

    @field_validator("base_price")
    @classmethod
    def validate_positive_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Price must be strictly positive, got {v}")
        return round(v, 2)


class RawStoreCluster(BaseModel):
    """Raw store cluster assignment."""
    store_id: str = Field(..., min_length=1)
    cluster_id: str = Field(..., min_length=1)
    region: str | None = Field(default=None)
    store_tier: str | None = Field(default=None)


class RawHolidayEvent(BaseModel):
    """Raw holiday calendar event."""
    week_start_date: date = Field(..., description="Monday-aligned trading week start")
    fiscal_year: int = Field(..., ge=2020, le=2035)
    fiscal_week: int = Field(..., ge=1, le=53)
    is_holiday_week: int = Field(..., ge=0, le=1)
    holiday_name: str | None = Field(default=None)


class RawWeeklySale(BaseModel):
    """Raw historical weekly sales observation."""
    sku_id: str = Field(..., min_length=1)
    store_id: str = Field(..., min_length=1)
    week_start_date: date = Field(..., description="Trading week date")
    units_sold: float = Field(..., ge=0.0, description="Gross sales quantity")
    revenue: float | None = Field(default=None, ge=0.0)
    # Optional stockout indicators - if unobserved, MUST remain None (not fabricated)
    days_in_stock: int | None = Field(default=None, ge=0, le=7)
    is_stockout: bool | None = Field(default=None)


# ==============================================================================
# Processed Feature Record Schema
# ==============================================================================

class ProcessedFeatureRecord(BaseModel):
    """Standardized multi-horizon feature vector for training and cold-start inference."""
    sku_id: str
    store_id: str | None = None
    cluster_id: str | None = None
    launch_week_age: int = Field(..., ge=1, le=8, description="Introductory week 1-8")
    
    # Categorical attributes (normalized)
    category: str
    subcategory: str
    colour: str
    material: str
    price_band: str
    brand_tier: str
    
    # Numerical & Financial attributes
    base_price: float
    log_base_price: float
    
    # Temporal & Launch features
    launch_month: int = Field(..., ge=1, le=12)
    sin_launch_month: float
    cos_launch_month: float
    
    # Marketing feature (validated against launch burst business rule)
    marketing_flag: int = Field(..., ge=0, le=1)
    
    # Calendar & Holiday features
    is_holiday_week: int
    holiday_name: str
    week_of_year: int
    sin_week_of_year: float
    cos_week_of_year: float
    
    # Observation provenance
    observation_status: ObservationStatus
    is_target_eval_sku: bool
    
    # Target (None during inference to prevent data leakage)
    units_sold: float | None = None
