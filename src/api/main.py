"""FastAPI Application Entry Point for R4 New Product Demand Forecasting Platform."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from src.api.middleware import (
    RateLimitMiddleware,
    RequestTrackingMiddleware,
    register_exception_handlers,
)
from src.api.routes import (
    audit,
    data,
    forecasts,
    health,
    inventory,
    jobs,
    models,
    monitoring,
    reports,
)
from src.core.config import settings
from src.core.logging import get_logger
from src.db.models import ForecastRunModel
from src.db.session import async_session_scope

logger = get_logger("api_main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and graceful shutdown."""
    logger.info(
        f"Initializing R4 Demand Forecasting Backend (Environment: {settings.environment}, "
        f"Horizon: {settings.evaluation_horizon_weeks}w, Target SKUs: {settings.num_evaluation_skus})"
    )

    # FL-11: Recover from ungraceful crashes by transitioning orphaned RUNNING runs to FAILED
    try:
        async with async_session_scope() as session:
            res = await session.execute(
                update(ForecastRunModel)
                .where(ForecastRunModel.status == "RUNNING")
                .values(
                    status="FAILED",
                    execution_metadata={"error": "Process terminated unexpectedly; cleaned up on server restart"},
                )
            )
            row_count = getattr(res, "rowcount", None)
            if row_count and row_count > 0:
                logger.warning(f"Cleaned up {row_count} zombie RUNNING forecast run(s) on startup.")
    except Exception as exc:
        logger.warning(f"Startup zombie cleanup check skipped or encountered error: {exc}")

    yield
    logger.info("Shutting down R4 Demand Forecasting Backend.")


def create_application() -> FastAPI:
    """FastAPI application factory configuring OpenAPI documentation, routes, and middleware."""
    app = FastAPI(
        title="R4 New Product Demand Forecasting API",
        description=(
            "Production-grade backend for cold-start retail SKU demand forecasting, "
            "conformal prediction intervals, single-period Newsvendor inventory optimization, "
            "TreeSHAP explainability, and multi-indicator confidence scoring."
        ),
        version="0.9.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health & Readiness", "description": "Liveness and readiness probes."},
            {"name": "Data Pipeline & Ingestion", "description": "Secure file import and validation."},
            {"name": "Model Registry & Training", "description": "Model versioning and asynchronous training."},
            {"name": "Forecasting & Predictions", "description": "Supervised predictions, conformal intervals, and analogues."},
            {"name": "Inventory Optimization", "description": "Newsvendor order quantities and financial cost optimization."},
            {"name": "Executive Reports & Evaluation", "description": "Official WAPE benchmarks and executive portfolio reports."},
            {"name": "Background Jobs", "description": "Asynchronous job polling and progress tracking."},
        ],
    )

    # 1. Register Exception Handlers & Request Correlation Middleware
    register_exception_handlers(app)
    app.add_middleware(RequestTrackingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=300, heavy_route_rpm=50)

    # 2. Configure CORS
    origins = [orig.strip() for orig in settings.allowed_origins.split(",") if orig.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-MS"],
    )

    # 3. Root Level Health Probes
    app.include_router(health.router)

    # 4. Versioned API Routes (/api/v1)
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(audit.router, prefix=settings.api_prefix)
    app.include_router(data.router, prefix=settings.api_prefix)
    app.include_router(models.router, prefix=settings.api_prefix)
    app.include_router(forecasts.router, prefix=settings.api_prefix)
    app.include_router(inventory.router, prefix=settings.api_prefix)
    app.include_router(reports.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)
    app.include_router(monitoring.router, prefix=settings.api_prefix)

    return app


app = create_application()


def start() -> None:
    """CLI launcher for uvicorn server."""
    uvicorn.run(
        "src.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.environment == "development"),
    )


if __name__ == "__main__":
    start()
