"""FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.api.routes import audit, forecast, health
from src.core.config import settings
from src.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown procedures."""
    logger.info("Initializing R4 Demand Forecasting Service (Environment: %s)", settings.environment)
    logger.info("Configured Evaluation Horizon: %d Weeks | Target Evaluation SKUs: %d",
                settings.evaluation_horizon_weeks, settings.num_evaluation_skus)
    yield
    logger.info("Shutting down R4 Demand Forecasting Service.")


def create_application() -> FastAPI:
    """Factory function for FastAPI application instance."""
    app = FastAPI(
        title="R4 New Product Demand Forecasting API",
        description="Production API for cold-start demand forecasting across store clusters and holiday variations.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    origins = [orig.strip() for orig in settings.allowed_origins.split(",") if orig.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API Routers
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(audit.router, prefix=settings.api_prefix)
    app.include_router(forecast.router, prefix=settings.api_prefix)

    return app


app = create_application()


def start() -> None:
    """Entry point for CLI command 'r4-serve'."""
    uvicorn.run(
        "src.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.environment == "development"),
    )


if __name__ == "__main__":
    start()
