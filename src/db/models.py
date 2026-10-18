"""SQLAlchemy 2.0 Relational Data Model for R4 Demand Forecasting & Inventory Platform.

Normalized schema adhering to Phase 8 specifications:
- skus
- store_clusters
- holidays
- weekly_sales
- model_versions
- forecast_runs
- weekly_forecasts
- analogue_matches
- inventory_recommendations
- cluster_allocations
- data_manifests
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy entities."""
    pass


# Use standard JSON type compatible with PostgreSQL JSONB and SQLite JSON
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class SKUModel(Base):
    """Normalized master product catalogue entity."""
    __tablename__ = "skus"

    sku_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subcategory: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    colour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    launch_date: Mapped[date] = mapped_column(Date, nullable=False)
    has_marketing_support: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_evaluation_sku: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    sales: Mapped[list["WeeklySalesModel"]] = relationship("WeeklySalesModel", back_populates="sku", cascade="all, delete-orphan")
    forecasts: Mapped[list["WeeklyForecastModel"]] = relationship("WeeklyForecastModel", back_populates="sku", cascade="all, delete-orphan")
    recommendations: Mapped[list["InventoryRecommendationModel"]] = relationship("InventoryRecommendationModel", back_populates="sku", cascade="all, delete-orphan")


class StoreClusterModel(Base):
    """Retail store network clustering classification."""
    __tablename__ = "store_clusters"

    cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cluster_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    store_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    regional_climate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    income_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    sales: Mapped[list["WeeklySalesModel"]] = relationship("WeeklySalesModel", back_populates="cluster")


class HolidayModel(Base):
    """Retail promotional and statutory holiday calendar."""
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    holiday_name: Mapped[str] = mapped_column(String(128), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_of_year: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_promotional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("holiday_name", "holiday_date", name="uq_holiday_name_date"),
    )


class WeeklySalesModel(Base):
    """Realized weekly POS sales across historical mature SKUs."""
    __tablename__ = "weekly_sales"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False, index=True)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(64), ForeignKey("store_clusters.cluster_id"), nullable=False, index=True)
    launch_week_age: Mapped[int] = mapped_column(Integer, nullable=False)
    units_sold: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    week_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    sku: Mapped["SKUModel"] = relationship("SKUModel", back_populates="sales")
    cluster: Mapped["StoreClusterModel"] = relationship("StoreClusterModel", back_populates="sales")

    __table_args__ = (
        UniqueConstraint("sku_id", "store_id", "launch_week_age", name="uq_weekly_sales_sku_store_week"),
        Index("ix_sales_sku_week", "sku_id", "launch_week_age"),
    )


class ModelVersionModel(Base):
    """Registered and versioned machine learning forecasting models."""
    __tablename__ = "model_versions"

    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(String(64), nullable=False)
    target_transform: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    training_manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_wape: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    hyperparameters: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    feature_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    runs: Mapped[list["ForecastRunModel"]] = relationship("ForecastRunModel", back_populates="model_version")


class ForecastRunModel(Base):
    """Execution record for a batch or official forecast generation run."""
    __tablename__ = "forecast_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_versions.model_id"), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="EVALUATION_150")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    input_manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sku_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overall_wape: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    overall_bias_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    reproducibility_seed: Mapped[int] = mapped_column(Integer, default=42, nullable=False)
    execution_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    model_version: Mapped["ModelVersionModel"] = relationship("ModelVersionModel", back_populates="runs")
    weekly_forecasts: Mapped[list["WeeklyForecastModel"]] = relationship("WeeklyForecastModel", back_populates="run", cascade="all, delete-orphan")
    analogue_matches: Mapped[list["AnalogueMatchModel"]] = relationship("AnalogueMatchModel", back_populates="run", cascade="all, delete-orphan")
    recommendations: Mapped[list["InventoryRecommendationModel"]] = relationship("InventoryRecommendationModel", back_populates="run", cascade="all, delete-orphan")


class WeeklyForecastModel(Base):
    """Weekly point forecasts and calibrated conformal prediction intervals."""
    __tablename__ = "weekly_forecasts"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("forecast_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False, index=True)
    horizon_week: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_sales: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    lower_bound_80: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    upper_bound_80: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    lower_bound_90: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    upper_bound_90: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run: Mapped["ForecastRunModel"] = relationship("ForecastRunModel", back_populates="weekly_forecasts")
    sku: Mapped["SKUModel"] = relationship("SKUModel", back_populates="forecasts")

    __table_args__ = (
        UniqueConstraint("run_id", "sku_id", "horizon_week", name="uq_forecast_run_sku_week"),
        Index("ix_forecasts_run_sku", "run_id", "sku_id"),
    )


class AnalogueMatchModel(Base):
    """Top-K similar historical products supporting cold-start forecasts."""
    __tablename__ = "analogue_matches"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("forecast_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    query_sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False, index=True)
    analogue_sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    observed_curve: Mapped[list[float] | None] = mapped_column(JSON_TYPE, nullable=True)

    # Relationships
    run: Mapped["ForecastRunModel"] = relationship("ForecastRunModel", back_populates="analogue_matches")

    __table_args__ = (
        UniqueConstraint("run_id", "query_sku_id", "rank", name="uq_analogue_run_query_rank"),
    )


class InventoryRecommendationModel(Base):
    """Newsvendor initial buy quantity and cost optimization outputs."""
    __tablename__ = "inventory_recommendations"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("forecast_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String(32), default="BASE", nullable=False)
    forecast_cumulative_8w: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    recommended_buy_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unconstrained_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    critical_ratio: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    understock_cost_cu: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    overstock_cost_co: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    expected_shortage_units: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    expected_excess_units: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    expected_total_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    expected_fill_rate_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    confidence_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    explanation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run: Mapped["ForecastRunModel"] = relationship("ForecastRunModel", back_populates="recommendations")
    sku: Mapped["SKUModel"] = relationship("SKUModel", back_populates="recommendations")
    cluster_allocations: Mapped[list["ClusterAllocationModel"]] = relationship("ClusterAllocationModel", back_populates="recommendation", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("run_id", "sku_id", "scenario", name="uq_inventory_run_sku_scenario"),
    )


class ClusterAllocationModel(Base):
    """Optional store-cluster inventory breakdown for an approved recommendation."""
    __tablename__ = "cluster_allocations"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory_recommendations.id", ondelete="CASCADE"), nullable=False, index=True)
    sku_id: Mapped[str] = mapped_column(String(64), ForeignKey("skus.sku_id", ondelete="CASCADE"), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(64), ForeignKey("store_clusters.cluster_id"), nullable=False)
    allocated_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_weight: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)

    # Relationships
    recommendation: Mapped["InventoryRecommendationModel"] = relationship("InventoryRecommendationModel", back_populates="cluster_allocations")

    __table_args__ = (
        UniqueConstraint("recommendation_id", "cluster_id", name="uq_alloc_rec_cluster"),
    )


class DataManifestModel(Base):
    """Data lineage and cryptographic provenance audit log."""
    __tablename__ = "data_manifests"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    manifest_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
