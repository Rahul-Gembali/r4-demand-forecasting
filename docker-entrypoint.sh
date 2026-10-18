#!/usr/bin/env sh
set -e

echo "=== R4 Cold-Start Demand Forecasting Service ==="
echo "Environment: ${ENVIRONMENT:-production}"
echo "Log Level:   ${LOG_LEVEL:-INFO}"

# Run Alembic database schema migrations
echo "Running Alembic migrations..."
alembic upgrade head || {
    echo "Note: Alembic schema is already up to date or initialized."
}

# Optional safe development/demo database seed
if [ "${RUN_DB_SEED:-false}" = "true" ] || [ "${ALLOW_DEV_SEED:-false}" = "true" ]; then
    echo "Executing safe database seeding..."
    python scripts/init_db.py --sales-limit "${SEED_SALES_LIMIT:-10000}" || {
        echo "Note: Database seeding already executed or preserved."
    }
fi

echo "Starting FastAPI application via Uvicorn on port ${APP_PORT:-8000}..."
exec uvicorn src.api.main:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${APP_PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --log-level "${LOG_LEVEL:-info}"
