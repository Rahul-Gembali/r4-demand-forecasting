"""Comprehensive integration tests for Phase 9: FastAPI Backend Endpoints."""

import asyncio
from datetime import date, datetime, timezone
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.api.main import app
from src.core.config import settings
from src.db.models import Base
from src.db.repository import ForecastRepository
from src.db.session import create_async_db_engine, get_db_session, init_db_schema

ADMIN_HEADERS = {"X-API-Key": settings.api_key_admin}
OPERATOR_HEADERS = {"X-API-Key": settings.api_key_operator}
VIEWER_HEADERS = {"X-API-Key": settings.api_key_viewer}


@pytest.fixture
def api_client(tmp_path: Path):
    """Fixture providing isolated database, seeded reference run, and FastAPI TestClient."""
    db_file = tmp_path / "test_api_database.db"
    engine = create_async_db_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}", echo=False)

    async def setup_test_database():
        await init_db_schema(engine)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            repo = ForecastRepository(session)

            # 1. Clusters & SKUs
            await repo.bulk_insert_store_clusters(
                [{"cluster_id": "CL_TEST_1", "cluster_name": "Flagship", "store_count": 3}]
            )
            await repo.upsert_sku(
                {
                    "sku_id": "SKU_EVAL_001",
                    "product_name": "Test Sneakers Grey",
                    "category": "Footwear",
                    "subcategory": "Sneakers",
                    "base_price": 104.60,
                    "launch_date": date(2025, 1, 1),
                    "is_evaluation_sku": True,
                }
            )
            await repo.upsert_sku(
                {
                    "sku_id": "SKU_EVAL_002",
                    "product_name": "Test Belts Red",
                    "category": "Accessories",
                    "subcategory": "Belts",
                    "base_price": 165.34,
                    "launch_date": date(2025, 1, 1),
                    "is_evaluation_sku": True,
                }
            )

            # 2. Model Version
            await repo.create_model_version(
                {
                    "model_id": "v1.0.0-catboost-coldstart",
                    "algorithm": "CatBoostRegressor",
                    "objective": "MAE",
                    "target_transform": "log1p",
                    "artifact_path": "artifacts/models/test/model.cbm",
                    "validation_wape": 0.2561,
                    "hyperparameters": {"iterations": 300, "depth": 6},
                    "feature_schema": {"features": ["launch_week_age", "base_price"]},
                }
            )

            # 3. Forecast Run RUN_EVAL_150_V1
            await repo.create_forecast_run(
                {
                    "run_id": "RUN_EVAL_150_V1",
                    "model_id": "v1.0.0-catboost-coldstart",
                    "status": "COMPLETED",
                    "sku_count": 2,
                    "overall_wape": 0.2561,
                    "overall_bias_pct": -3.76,
                    "completed_at": datetime.now(timezone.utc),
                }
            )

            # 4. Weekly Forecasts
            forecasts = []
            for w in range(1, 9):
                forecasts.append(
                    {
                        "sku_id": "SKU_EVAL_001",
                        "horizon_week": w,
                        "predicted_sales": 80.0 - w * 4,
                        "lower_bound_80": 60.0 - w * 4,
                        "upper_bound_80": 100.0 - w * 4,
                        "lower_bound_90": 50.0 - w * 4,
                        "upper_bound_90": 110.0 - w * 4,
                    }
                )
            await repo.save_weekly_forecasts("RUN_EVAL_150_V1", forecasts)

            # 5. Inventory Recommendations
            await repo.save_inventory_recommendations(
                "RUN_EVAL_150_V1",
                [
                    {
                        "sku_id": "SKU_EVAL_001",
                        "scenario": "BASE",
                        "forecast_cumulative_8w": 501.4,
                        "recommended_buy_quantity": 522,
                        "critical_ratio": 0.6286,
                        "understock_cost_cu": 47.07,
                        "overstock_cost_co": 36.61,
                        "expected_shortage_units": 18.14,
                        "expected_excess_units": 38.74,
                        "expected_total_cost": 2360.76,
                        "expected_fill_rate_pct": 96.38,
                        "confidence_score": 46.2,
                        "confidence_tier": "LOW",
                        "explanation_summary": "Low confidence due to wide intervals.",
                        "assumptions": {"min_order_qty": 50, "case_pack_size": 6},
                    },
                    {
                        "sku_id": "SKU_EVAL_002",
                        "scenario": "BASE",
                        "forecast_cumulative_8w": 721.27,
                        "recommended_buy_quantity": 750,
                        "critical_ratio": 0.6286,
                        "understock_cost_cu": 74.40,
                        "overstock_cost_co": 57.87,
                        "expected_shortage_units": 24.46,
                        "expected_excess_units": 53.19,
                        "expected_total_cost": 5082.23,
                        "expected_fill_rate_pct": 96.61,
                        "confidence_score": 85.0,
                        "confidence_tier": "HIGH",
                        "explanation_summary": "High confidence forecast.",
                        "assumptions": {"min_order_qty": 50, "case_pack_size": 6},
                    },
                ],
            )

            # 6. Analogue Matches
            await repo.save_analogue_matches(
                "RUN_EVAL_150_V1",
                [
                    {
                        "query_sku_id": "SKU_EVAL_001",
                        "analogue_sku_id": "SKU_HIST_0417",
                        "rank": 1,
                        "similarity_score": 0.8982,
                        "observed_curve": [45.0, 78.0, 94.0, 39.0, 50.0, 34.0, 56.0, 56.0],
                    }
                ],
            )

            # 7. Data Manifest
            await repo.record_data_manifest(
                {
                    "manifest_type": "TEST_DATA",
                    "file_identifier": "data/test.csv",
                    "sha256_checksum": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                    "row_count": 2,
                    "schema_snapshot": {"test": True},
                }
            )

            await session.commit()

    asyncio.run(setup_test_database())

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db_session] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


# =============================================================================
# 1. HEALTH AND READINESS PROBES
# =============================================================================

def test_liveness_probe_root_and_versioned(api_client: TestClient):
    """Test GET /health and GET /api/v1/health."""
    for path in ["/health", "/api/v1/health"]:
        res = api_client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "r4-demand-forecasting" in data["service"]


def test_readiness_probe_root_and_versioned(api_client: TestClient):
    """Test GET /ready and GET /api/v1/ready."""
    for path in ["/ready", "/api/v1/ready"]:
        res = api_client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["ready"] is True
        assert data["components"]["database"]["status"] == "UP"


# =============================================================================
# 2. AUTHENTICATION & ROLE-BASED ACCESS CONTROL
# =============================================================================

def test_unauthenticated_request_rejected(api_client: TestClient):
    """Endpoints requiring authentication return 401 when missing credentials."""
    res = api_client.get("/api/v1/models")
    assert res.status_code == 401
    assert "Missing API authentication credentials" in res.json()["error"]["message"]


def test_invalid_api_key_rejected(api_client: TestClient):
    """Endpoints reject invalid API keys with 401 Unauthorized."""
    res = api_client.get("/api/v1/models", headers={"X-API-Key": "invalid-dummy-key"})
    assert res.status_code == 401
    assert "Invalid API authentication token" in res.json()["error"]["message"]


def test_role_based_access_control_viewer_forbidden_on_write(api_client: TestClient):
    """Viewer role cannot access admin endpoints like model training or data import."""
    # Viewer attempting to train a model -> 403 Forbidden
    res = api_client.post(
        "/api/v1/models/train",
        headers=VIEWER_HEADERS,
        json={"algorithm": "CatBoostRegressor", "iterations": 50},
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["error"]["message"]


def test_bearer_token_authorization(api_client: TestClient):
    """Authenticate successfully via Authorization: Bearer <key>."""
    bearer_headers = {"Authorization": f"Bearer {settings.api_key_viewer}"}
    res = api_client.get("/api/v1/models", headers=bearer_headers)
    assert res.status_code == 200


# =============================================================================
# 3. SECURE FILE UPLOAD & INGESTION
# =============================================================================

def test_secure_data_import_csv(api_client: TestClient):
    """Test importing new SKU attributes from a valid CSV upload."""
    csv_content = (
        "sku_id,product_name,category,subcategory,colour,material,base_price,brand,launch_date\n"
        "SKU_IMPORT_01,Imported Jacket,Apparel,Jackets,Navy,Wool,145.0,Luxura,2025-04-01\n"
        "SKU_IMPORT_02,Imported Boots,Footwear,Boots,Brown,Leather,180.0,Zenith,2025-04-01\n"
    )
    files = {"file": ("new_products.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"manifest_type": "NEW_SKUS", "is_evaluation_data": "true"}

    res = api_client.post("/api/v1/data/import", headers=OPERATOR_HEADERS, files=files, data=data)
    assert res.status_code == 201
    resp_data = res.json()
    assert resp_data["rows_parsed"] == 2
    assert resp_data["skus_upserted"] == 2
    assert resp_data["is_evaluation_data"] is True
    assert len(resp_data["sha256_checksum"]) == 64


def test_import_unsupported_file_extension(api_client: TestClient):
    """Reject disallowed executable or script extensions with 415."""
    files = {"file": ("malicious.exe", io.BytesIO(b"binary content"), "application/octet-stream")}
    res = api_client.post("/api/v1/data/import", headers=OPERATOR_HEADERS, files=files)
    assert res.status_code == 415
    assert "Unsupported file extension" in res.json()["error"]["message"]


def test_import_path_traversal_sanitized(api_client: TestClient):
    """Ensure path traversal attempts are safely sanitized to simple basenames."""
    csv_content = "sku_id,category,base_price\nSKU_TRAV_1,Apparel,75.0\n"
    # Malicious filename attempting path traversal
    files = {"file": ("../../etc/passwd.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

    res = api_client.post("/api/v1/data/import", headers=OPERATOR_HEADERS, files=files)
    assert res.status_code == 201
    assert ".." not in res.json()["filename"]


# =============================================================================
# 4. MODEL REGISTRY & ASYNCHRONOUS TRAINING
# =============================================================================

def test_list_models(api_client: TestClient):
    """Test GET /api/v1/models returns registered model versions."""
    res = api_client.get("/api/v1/models", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert data["models"][0]["model_id"] == "v1.0.0-catboost-coldstart"
    assert data["models"][0]["algorithm"] == "CatBoostRegressor"


def test_train_model_async_dispatch(api_client: TestClient):
    """Test POST /api/v1/models/train dispatches asynchronous background job."""
    payload = {
        "algorithm": "CatBoostRegressor",
        "objective": "MAE",
        "target_transform": "log1p",
        "iterations": 20,
        "learning_rate": 0.05,
        "depth": 4,
    }
    res = api_client.post("/api/v1/models/train", headers=ADMIN_HEADERS, json=payload)
    assert res.status_code == 202
    job_data = res.json()
    assert "JOB_" in job_data["job_id"]
    assert job_data["status"] in ["PENDING", "RUNNING", "COMPLETED"]


def test_train_model_invalid_hyperparameters(api_client: TestClient):
    """Reject out-of-bounds hyperparameter payload with 422."""
    payload = {
        "algorithm": "CatBoostRegressor",
        "iterations": -10,  # Invalid: ge=10
        "learning_rate": 2.5,  # Invalid: le=1.0
    }
    res = api_client.post("/api/v1/models/train", headers=ADMIN_HEADERS, json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 5. ASYNCHRONOUS JOB POLLING
# =============================================================================

def test_job_status_polling(api_client: TestClient):
    """Dispatch job and poll GET /api/v1/jobs/{job_id}."""
    train_res = api_client.post(
        "/api/v1/models/train",
        headers=ADMIN_HEADERS,
        json={"algorithm": "CatBoostRegressor", "iterations": 15},
    )
    job_id = train_res.json()["job_id"]

    res = api_client.get(f"/api/v1/jobs/{job_id}", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    assert res.json()["job_id"] == job_id
    assert res.json()["status"] in ["PENDING", "RUNNING", "COMPLETED"]


def test_nonexistent_job_returns_404(api_client: TestClient):
    """Polling a non-existent job ID returns 404 Not Found."""
    res = api_client.get("/api/v1/jobs/JOB_DOES_NOT_EXIST", headers=VIEWER_HEADERS)
    assert res.status_code == 404


# =============================================================================
# 6. FORECAST BATCH RUNS & EXECUTION
# =============================================================================

def test_get_forecast_run_summary(api_client: TestClient):
    """Test GET /api/v1/forecasts/{run_id} returns executive metrics."""
    res = api_client.get("/api/v1/forecasts/RUN_EVAL_150_V1", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "RUN_EVAL_150_V1"
    assert data["status"] == "COMPLETED"
    assert data["sku_count"] == 2
    assert data["total_recommended_buy_units"] == 522 + 750
    assert data["average_confidence_score"] > 0.0


def test_get_nonexistent_forecast_run_returns_404(api_client: TestClient):
    """Querying non-existent forecast run returns 404."""
    res = api_client.get("/api/v1/forecasts/RUN_NONEXISTENT", headers=VIEWER_HEADERS)
    assert res.status_code == 404


def test_create_forecast_run_duplicate_blocked(api_client: TestClient):
    """Attempting to overwrite a completed run with duplicate run_id returns 409 Conflict."""
    res = api_client.post(
        "/api/v1/forecasts",
        headers=OPERATOR_HEADERS,
        json={"run_id": "RUN_EVAL_150_V1", "async_mode": False},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "DUPLICATE_RUN_CONFLICT"


# =============================================================================
# 7. SKU DETAIL FORECASTS & CONFIDENCE RANKING
# =============================================================================

def test_get_sku_forecast_detail(api_client: TestClient):
    """Test GET /api/v1/forecasts/{run_id}/skus/{sku_id} returns full prediction package."""
    res = api_client.get(
        "/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_EVAL_001", headers=VIEWER_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sku_id"] == "SKU_EVAL_001"
    assert len(data["forecasts"]) == 8
    assert data["forecasts"][0]["predicted_sales"] > 0
    assert data["forecasts"][0]["lower_bound_80"] <= data["forecasts"][0]["upper_bound_80"]
    assert data["recommendation"]["recommended_buy_quantity"] == 522
    assert len(data["analogues"]) >= 1
    assert data["analogues"][0]["similarity_score"] > 0.8


def test_get_sku_forecast_nonexistent_sku(api_client: TestClient):
    """Querying an unknown SKU returns 404."""
    res = api_client.get(
        "/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_NOT_EXIST", headers=VIEWER_HEADERS
    )
    assert res.status_code == 404


def test_get_low_confidence_skus(api_client: TestClient):
    """Test GET /api/v1/forecasts/{run_id}/low-confidence retrieves least-confident items."""
    res = api_client.get(
        "/api/v1/forecasts/RUN_EVAL_150_V1/low-confidence?limit=5", headers=VIEWER_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "RUN_EVAL_150_V1"
    assert data["count"] >= 1
    # Lowest score first: SKU_EVAL_001 (score 46.2) precedes SKU_EVAL_002 (score 85.0)
    assert data["items"][0]["sku_id"] == "SKU_EVAL_001"
    assert data["items"][0]["confidence_tier"] == "LOW"


# =============================================================================
# 8. INVENTORY OPTIMIZATION SCENARIOS
# =============================================================================

def test_inventory_optimize_custom_scenario(api_client: TestClient):
    """Test POST /api/v1/inventory/optimize with custom cost and packing constraints."""
    payload = {
        "run_id": "RUN_EVAL_150_V1",
        "scenario_name": "CONSERVATIVE",
        "understock_cost_cu": 25.0,
        "overstock_cost_co": 50.0,  # High overstock penalty -> critical ratio = 25 / 75 = 0.33
        "min_order_quantity": 60,
        "case_pack_size": 12,
    }
    res = api_client.post("/api/v1/inventory/optimize", headers=OPERATOR_HEADERS, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "RUN_EVAL_150_V1"
    assert data["scenario_name"] == "CONSERVATIVE"
    assert data["total_skus_optimized"] == 2
    assert data["total_buy_units"] > 0
    # Every recommended quantity must be a multiple of case_pack_size (12)
    for item in data["recommendations"]:
        assert item["recommended_buy_quantity"] % 12 == 0


# =============================================================================
# 9. EXECUTIVE REPORTS & AUDIT LINEAGE
# =============================================================================

def test_get_run_report(api_client: TestClient):
    """Test GET /api/v1/reports/{run_id} returns executive report package."""
    res = api_client.get("/api/v1/reports/RUN_EVAL_150_V1", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "RUN_EVAL_150_V1"
    assert data["portfolio_metrics"]["overall_wape"] == 0.2561
    assert "conformal_method" in data["uncertainty_calibration"]
    assert data["inventory_summary"]["total_recommended_buy_units"] == 522 + 750
    assert len(data["least_confident_skus_summary"]) >= 1
    assert len(data["data_manifests"]) >= 1


# =============================================================================
# 10. STRICT DATA ISOLATION VERIFICATION
# =============================================================================

def test_never_expose_hidden_evaluation_actuals(api_client: TestClient):
    """Verify that hidden actual sales labels are never leaked in API response payloads."""
    res = api_client.get(
        "/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_EVAL_001", headers=VIEWER_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    # Forecast payload must contain predictions and bounds, not ground-truth units_sold
    assert "units_sold" not in data
    for fc in data["forecasts"]:
        assert "units_sold" not in fc
        assert "actual_sales" not in fc
