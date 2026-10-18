# =============================================================================
# R4 Cold-Start Retail Demand Forecasting - FastAPI Backend Dockerfile
# Multi-stage optimized, non-root user, health check equipped
# =============================================================================

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_PORT=8000 \
    APP_HOST=0.0.0.0

WORKDIR /app

# Install minimal system dependencies required for compiling wheels and health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create application user for security hardening
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -m appuser

# Copy application directories and files
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY migrations/ /app/migrations/
COPY artifacts/ /app/artifacts/
COPY data/ /app/data/
COPY alembic.ini /app/alembic.ini
COPY pyproject.toml /app/pyproject.toml
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

# Ensure required runtime directories exist with correct permissions
RUN mkdir -p /app/data/uploads /app/logs && \
    chmod +x /app/docker-entrypoint.sh && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Docker healthcheck querying standard liveness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
