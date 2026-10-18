"""Pydantic V2 Request and Response Schemas for R4 Forecasting API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# SYSTEM HEALTH & READINESS SCHEMAS
# =============================================================================

class HealthResponse(BaseModel):
    """Liveness probe response."""
    status: str = Field(default="healthy", description="Service health state")
    service: str = Field(default="r4-demand-forecasting", description="Service identifier")
    version: str = Field(default="0.1.0", description="API semantic version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp")


class ReadinessComponent(BaseModel):
    """Component status breakdown."""
    status: str = Field(..., description="Operational status: UP or DOWN")
    details: str = Field(..., description="Diagnostic details or latency")


class ReadinessResponse(BaseModel):
    """Readiness probe response indicating system availability."""
    ready: bool = Field(..., description="Whether system is ready to serve traffic")
    components: dict[str, ReadinessComponent] = Field(..., description="Health of underlying dependencies")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# DATA IMPORT SCHEMAS
# =============================================================================

class DataImportSummary(BaseModel):
    """Summary of data ingestion operation."""
    filename: str = Field(..., description="Original name of uploaded file")
    manifest_type: str = Field(..., description="Target dataset type (e.g. NEW_SKUS, MATURE_SKUS)")
    rows_parsed: int = Field(..., ge=0, description="Total valid rows imported")
    skus_upserted: int = Field(..., ge=0, description="Count of SKUs persisted in catalogue")
    sha256_checksum: str = Field(..., description="Cryptographic SHA256 checksum")
    is_evaluation_data: bool = Field(..., description="Flag marking candidate cold-start items")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal validation warnings")


# =============================================================================
# MODEL REGISTRY & TRAINING SCHEMAS
# =============================================================================

class TrainModelRequest(BaseModel):
    """Parameters for model training execution."""
    algorithm: str = Field(default="CatBoostRegressor", description="Model architecture")
    objective: str = Field(default="MAE", description="Loss objective (MAE, L1, RMSE)")
    target_transform: str = Field(default="log1p", description="Target transformation")
    iterations: int = Field(default=300, ge=10, le=2000, description="Number of boosting iterations")
    learning_rate: float = Field(default=0.03, gt=0.0, le=1.0, description="Learning rate")
    depth: int = Field(default=6, ge=2, le=10, description="Tree depth")
    l2_leaf_reg: float = Field(default=3.0, ge=0.0, description="L2 regularization")
    random_seed: int = Field(default=42, description="Random seed")

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"CatBoostRegressor", "LightGBM", "CatBoost"}
        if v not in allowed:
            raise ValueError(f"Algorithm '{v}' not supported. Choose from: {sorted(allowed)}")
        return v


class ModelVersionItem(BaseModel):
    """Registered model version summary."""
    model_id: str
    algorithm: str
    objective: str
    target_transform: str
    artifact_path: str
    training_manifest_sha256: str | None = None
    validation_wape: float | None = None
    hyperparameters: dict[str, Any] | None = None
    feature_schema: dict[str, Any] | None = None
    created_at: datetime


class ModelVersionsListResponse(BaseModel):
    """Response containing registered models."""
    models: list[ModelVersionItem]
    total: int


# =============================================================================
# FORECASTING & UNCERTAINTY SCHEMAS
# =============================================================================

class ForecastRunRequest(BaseModel):
    """Trigger forecast batch execution."""
    run_id: str | None = Field(default=None, description="Optional custom run ID. If None, auto-generated.")
    model_id: str | None = Field(default=None, description="Model version to use (defaults to latest active)")
    sku_ids: list[str] | None = Field(default=None, description="Optional specific candidate SKU IDs to forecast")
    async_mode: bool = Field(default=False, description="Whether to execute asynchronously via background job")
    reproducibility_seed: int = Field(default=42, description="Random seed")


class ForecastRunResponse(BaseModel):
    """Execution status of a forecast batch run."""
    run_id: str
    model_id: str
    status: str
    sku_count: int
    created_at: datetime
    completed_at: datetime | None = None
    overall_wape: float | None = None
    overall_bias_pct: float | None = None
    total_recommended_buy_units: int = 0
    total_expected_cost: float = 0.0
    average_confidence_score: float = 0.0
    average_fill_rate_pct: float = 0.0


class WeeklyForecastItem(BaseModel):
    """Weekly point prediction with calibrated conformal uncertainty bounds."""
    horizon_week: int = Field(..., ge=1, le=8)
    predicted_sales: float = Field(..., ge=0.0)
    lower_bound_80: float | None = None
    upper_bound_80: float | None = None
    lower_bound_90: float | None = None
    upper_bound_90: float | None = None


class AnalogueMatchDetail(BaseModel):
    """Nearest historical precedent product."""
    rank: int
    analogue_sku_id: str
    similarity_score: float
    observed_curve: list[float] | None = None


class InventoryRecDetail(BaseModel):
    """Single-period Newsvendor buy recommendation."""
    scenario: str = "BASE"
    forecast_cumulative_8w: float
    recommended_buy_quantity: int
    critical_ratio: float
    understock_cost_cu: float
    overstock_cost_co: float
    expected_shortage_units: float
    expected_excess_units: float
    expected_total_cost: float
    expected_fill_rate_pct: float
    confidence_score: float | None = None
    confidence_tier: str | None = None
    explanation_summary: str | None = None
    assumptions: dict[str, Any] | None = None


class SKUForecastDetailResponse(BaseModel):
    """Comprehensive product-level forecast, uncertainty, analogue, and recommendation view."""
    sku_id: str
    product_name: str
    category: str
    subcategory: str
    colour: str | None = None
    material: str | None = None
    base_price: float
    brand: str | None = None
    brand_tier: str | None = None
    launch_date: str
    has_marketing_support: bool
    is_evaluation_sku: bool
    forecasts: list[WeeklyForecastItem]
    recommendation: InventoryRecDetail | None = None
    analogues: list[AnalogueMatchDetail] = Field(default_factory=list)


class SKUForecastListItem(BaseModel):
    """Summary item for SKU table in forecasting dashboard."""
    sku_id: str
    product_name: str
    category: str
    subcategory: str
    colour: str | None = None
    material: str | None = None
    base_price: float
    brand_tier: str | None = None
    launch_date: str
    has_marketing_support: bool
    is_evaluation_sku: bool
    total_projected_sales: float
    recommended_buy_quantity: int
    confidence_score: float | None = None
    confidence_tier: str | None = "MEDIUM"
    expected_total_cost: float | None = 0.0
    expected_fill_rate_pct: float | None = 85.0
    weekly_forecasts: list[float] = Field(default_factory=list)


class SKUForecastListResponse(BaseModel):
    """Paginated list of SKU forecast summaries."""
    run_id: str
    total: int
    items: list[SKUForecastListItem]



# =============================================================================
# CONFIDENCE RANKING SCHEMAS
# =============================================================================

class LowConfidenceSKUItem(BaseModel):
    """Product diagnosed with elevated forecast uncertainty."""
    sku_id: str
    product_name: str
    category: str
    subcategory: str
    base_price: float
    confidence_score: float
    confidence_tier: str
    forecast_cumulative_8w: float
    recommended_buy_quantity: int
    explanation_summary: str | None = None
    assumptions: dict[str, Any] | None = None


class LowConfidenceResponse(BaseModel):
    """List of least-confident products requiring human merchant review."""
    run_id: str
    count: int
    items: list[LowConfidenceSKUItem]


# =============================================================================
# INVENTORY OPTIMIZATION SCHEMAS
# =============================================================================

class InventoryOptimizeRequest(BaseModel):
    """Custom Newsvendor scenario parameters."""
    run_id: str = Field(..., description="Target forecast run ID")
    scenario_name: str = Field(default="CUSTOM", description="Scenario label (e.g. CONSERVATIVE, AGGRESSIVE, CUSTOM)")
    sku_ids: list[str] | None = Field(default=None, description="Optional SKU subset to optimize")
    understock_cost_cu: float | None = Field(default=None, gt=0.0, description="Override unit margin loss ($p - c$)")
    overstock_cost_co: float | None = Field(default=None, gt=0.0, description="Override unit salvage markdown ($c - s$)")
    min_order_quantity: int = Field(default=50, ge=0, description="Supplier minimum order quantity")
    case_pack_size: int = Field(default=6, ge=1, description="Supplier case-pack bundling constraint")


class InventoryOptimizeItem(BaseModel):
    """Result of optimization for a single SKU."""
    sku_id: str
    scenario: str
    recommended_buy_quantity: int
    critical_ratio: float
    expected_total_cost: float
    expected_fill_rate_pct: float


class InventoryOptimizeResponse(BaseModel):
    """Portfolio optimization summary."""
    run_id: str
    scenario_name: str
    total_skus_optimized: int
    total_buy_units: int
    total_expected_cost: float
    average_fill_rate_pct: float
    recommendations: list[InventoryOptimizeItem]


# =============================================================================
# EXECUTIVE & EVALUATION REPORT SCHEMAS
# =============================================================================

class ReportSummaryResponse(BaseModel):
    """Official performance and executive summary report."""
    run_id: str
    model_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    portfolio_metrics: dict[str, Any]
    uncertainty_calibration: dict[str, Any]
    inventory_summary: dict[str, Any]
    least_confident_skus_summary: list[dict[str, Any]]
    data_manifests: list[dict[str, Any]]


# =============================================================================
# ASYNCHRONOUS JOB MANAGEMENT SCHEMAS
# =============================================================================

class JobStatusResponse(BaseModel):
    """Asynchronous background job status and outcome."""
    job_id: str
    job_type: str
    status: str = Field(..., description="PENDING, RUNNING, COMPLETED, FAILED")
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    created_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


# =============================================================================
# ERROR ENVELOPE
# =============================================================================

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
