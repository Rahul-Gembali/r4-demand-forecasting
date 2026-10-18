"""Configuration settings for R4 Demand Forecasting."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment override support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: str = Field(default="development", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging verbosity")
    app_host: str = Field(default="0.0.0.0", description="API Host")
    app_port: int = Field(default=8000, description="API Port")
    api_prefix: str = Field(default="/api/v1", description="Prefix for API routes")
    secret_key: str = Field(default="dev-secret-key", description="Application secret")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Allowed CORS origins comma separated",
    )

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/r4_forecast.db",
        description="Database connection string (defaults to local SQLite; override with PostgreSQL in production)",
    )

    # Authentication & Security
    api_key_admin: str = Field(default="r4-admin-key-2026", description="Admin API Key")
    api_key_operator: str = Field(default="r4-operator-key-2026", description="Operator API Key")
    api_key_viewer: str = Field(default="r4-viewer-key-2026", description="Viewer Read-Only API Key")
    auth_enabled: bool = Field(default=True, description="Enable API key verification")
    max_upload_size_bytes: int = Field(default=52428800, description="Max upload file size in bytes (50MB)")
    data_uploads_dir: Path = Field(default=Path("./data/uploads"), description="Uploads sandbox directory")

    # File System Storage Paths
    data_raw_dir: Path = Field(default=Path("./data/raw"), description="Raw data directory")
    data_processed_dir: Path = Field(
        default=Path("./data/processed"), description="Processed data directory"
    )
    data_interim_dir: Path = Field(
        default=Path("./data/interim"), description="Interim data directory"
    )
    artifacts_dir: Path = Field(
        default=Path("./artifacts"), description="Artifacts & models directory"
    )

    # Problem Dimensions
    evaluation_horizon_weeks: int = Field(default=8, description="Forecast horizon in weeks")
    num_evaluation_skus: int = Field(default=150, description="Target evaluation SKU count")
    approx_historical_skus: int = Field(
        default=1200, description="Reference historical SKU count"
    )
    random_seed: int = Field(default=42, description="Global random seed")


settings = Settings()
