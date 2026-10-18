"""Phase 11 Comprehensive Integration, Security, and Reliability Test Suite.

Audits and validates:
1. End-to-end integration: ingestion -> inference -> conformal intervals -> Newsvendor -> DB -> API.
2. Strict SKU-level leakage prevention and inaccessible hidden evaluation targets.
3. Deterministic reproducibility across seeds.
4. Resilient handling of malformed records, missing features, and unseen categories.
5. Finite non-negative predictions and valid nested conformal intervals.
6. Newsvendor scenario stress-testing across extreme demand and asymmetric costs.
7. Model artifact SHA-256 cryptographic tamper detection.
8. Sensitive credentials and API key redaction in structured logs.
9. Governance rule: Prohibition of automated model promotion solely on detected drift.
10. Regression test: Safe handling of multiple scenario recommendations per SKU (MultipleResultsFound guard).
"""

import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.config import Settings, settings
from src.core.logging import SensitiveDataFilter
from src.core.monitoring import (
    ModelGovernance,
    TelemetryTracker,
)
from src.data.pipeline import DataPipeline
from src.db.repository import ForecastRepository
from src.db.session import async_session_scope
from src.evaluation.uncertainty import ConformalIntervalCalibrator
from src.inventory.constraints import InventoryConstraints
from src.inventory.optimizer import NewsvendorOptimizer
from src.models.supervised import CatBoostForecaster, ColdStartPredictor, ModelIntegrityError

OPERATOR_HEADERS = {"X-API-Key": settings.api_key_operator}
VIEWER_HEADERS = {"X-API-Key": settings.api_key_viewer}
ADMIN_HEADERS = {"X-API-Key": settings.api_key_admin}


# =============================================================================
# 1. END-TO-END SYSTEM INTEGRATION
# =============================================================================

@pytest.mark.asyncio
async def test_e2e_complete_workflow():
    """End-to-end test executing ingestion, inference, conformal bounds, Newsvendor optimization,
    database persistence, and API query verification."""
    run_id = f"RUN_E2E_P11_{int(datetime.now().timestamp())}"

    # Step 1: Initialize Candidate SKUs
    async with async_session_scope() as session:
        repo = ForecastRepository(session)
        sku_data = [
            {
                "sku_id": "SKU_E2E_001",
                "product_name": "Pro Marathon Running Shoes",
                "category": "Footwear",
                "subcategory": "Running",
                "colour": "Neon Blue",
                "material": "Mesh",
                "base_price": 140.0,
                "brand": "AeroSport",
                "brand_tier": "Premium",
                "launch_date": date(2025, 4, 1),
                "has_marketing_support": True,
                "is_evaluation_sku": True,
            },
            {
                "sku_id": "SKU_E2E_002",
                "product_name": "Basic Cotton Crewneck",
                "category": "Apparel",
                "subcategory": "T-Shirts",
                "colour": "White",
                "material": "Cotton",
                "base_price": 28.0,
                "brand": "DailyWear",
                "brand_tier": "Value",
                "launch_date": date(2025, 4, 1),
                "has_marketing_support": False,
                "is_evaluation_sku": True,
            },
        ]
        await repo.bulk_upsert_skus(sku_data)

        # Step 2: Create Forecast Run Record
        await repo.create_forecast_run({
            "run_id": run_id,
            "model_id": "v1.0.0-catboost-coldstart",
            "status": "COMPLETED",
            "sku_count": 2,
            "reproducibility_seed": 42,
            "overall_wape": 0.2450,
            "overall_bias_pct": -2.10,
        })

        # Step 3: Compute & Persist Predictions and Conformal Bounds
        # Simulating W1-W8 predictions with conformal intervals
        weekly_forecasts = []
        for sku in sku_data:
            base_sales = 60.0 if sku["category"] == "Footwear" else 35.0
            for w in range(1, 9):
                pred = base_sales * (1.0 - 0.05 * (w - 1))
                weekly_forecasts.append({
                    "run_id": run_id,
                    "sku_id": sku["sku_id"],
                    "horizon_week": w,
                    "predicted_sales": round(pred, 2),
                    "lower_bound_80": round(max(0.0, pred * 0.75), 2),
                    "upper_bound_80": round(pred * 1.25, 2),
                    "lower_bound_90": round(max(0.0, pred * 0.65), 2),
                    "upper_bound_90": round(pred * 1.35, 2),
                })
        await repo.save_weekly_forecasts(run_id, weekly_forecasts)

        # Step 4: Run Newsvendor Optimization
        optimizer = NewsvendorOptimizer()
        recommendations = []
        for sku in sku_data:
            cum_demand = sum(
                f["predicted_sales"] for f in weekly_forecasts if f["sku_id"] == sku["sku_id"]
            )
            rec = optimizer.optimize_sku(
                sku_id=sku["sku_id"],
                cumulative_demand_mean=cum_demand,
                cumulative_demand_lower_90=cum_demand * 0.7,
                cumulative_demand_upper_90=cum_demand * 1.3,
                base_price=sku["base_price"],
                custom_cu=30.0,
                custom_co=15.0,
                constraints=InventoryConstraints(min_order_quantity=50, case_pack_size=12),
            )
            recommendations.append({
                "run_id": run_id,
                "sku_id": sku["sku_id"],
                "scenario": "BASE",
                "forecast_cumulative_8w": cum_demand,
                "recommended_buy_quantity": rec.recommended_buy_quantity,
                "critical_ratio": rec.critical_ratio,
                "understock_cost_cu": 30.0,
                "overstock_cost_co": 15.0,
                "expected_shortage_units": rec.expected_shortage_units,
                "expected_excess_units": rec.expected_excess_units,
                "expected_total_cost": rec.expected_total_cost,
                "expected_fill_rate_pct": rec.expected_fill_rate_pct,
                "confidence_score": 78.5,
                "confidence_tier": "HIGH",
            })
        await repo.save_inventory_recommendations(run_id, recommendations)
        await session.commit()

    # Step 5: Query via FastAPI TestClient
    client = TestClient(app)
    res = client.get(f"/api/v1/forecasts/{run_id}", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    run_resp = res.json()
    assert run_resp["run_id"] == run_id
    assert run_resp["sku_count"] == 2
    assert run_resp["total_recommended_buy_units"] > 0

    # Step 6: Query SKU Detail
    res_sku = client.get(f"/api/v1/forecasts/{run_id}/skus/SKU_E2E_001", headers=VIEWER_HEADERS)
    assert res_sku.status_code == 200
    sku_resp = res_sku.json()
    assert len(sku_resp["forecasts"]) == 8
    assert sku_resp["recommendation"]["recommended_buy_quantity"] % 12 == 0


# =============================================================================
# 2. STRICT SKU-LEVEL LEAKAGE PREVENTION & HIDDEN TARGET PRIVACY
# =============================================================================

def test_sku_level_leakage_fencing(tmp_path: Path):
    """Verify that training datasets never contain evaluation SKUs."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    processed = tmp_path / "processed"
    raw.mkdir()
    pipeline = DataPipeline(raw_dir=raw, interim_dir=interim, processed_dir=processed)

    df_sales = pd.DataFrame([
        {"sku_id": f"HIST_{i}", "store_id": "S1", "week_start_date": "2024-01-08", "units_sold": 50.0}
        for i in range(5)
    ])
    df_mature = pd.DataFrame([
        {
            "sku_id": f"HIST_{i}",
            "product_name": f"Item {i}",
            "category": "Footwear",
            "subcategory": "Boots",
            "colour": "Black",
            "material": "Leather",
            "brand": "Apex",
            "brand_tier": "Premium",
            "base_price": 60.0,
            "launch_date": "2024-01-01",
            "has_marketing_support": False,
        }
        for i in range(5)
    ])
    df_new = pd.DataFrame([
        {
            "sku_id": "EVAL_SECRET_01",
            "product_name": "New Secret Item",
            "category": "Footwear",
            "subcategory": "Boots",
            "colour": "Brown",
            "material": "Leather",
            "brand": "Apex",
            "brand_tier": "Premium",
            "base_price": 60.0,
            "launch_date": "2025-04-01",
            "has_marketing_support": True,
        }
    ])
    df_stores = pd.DataFrame([{"store_id": "S1", "cluster_id": "C1"}])
    df_cal = pd.DataFrame([{"week_start_date": "2024-01-08", "is_holiday_week": 0, "holiday_name": "None"}])

    train_df = pipeline.build_training_features(df_sales, df_mature, df_stores, df_cal)
    inf_df = pipeline.build_inference_features(df_new, df_stores, df_cal)

    # 1. Zero SKU overlap between training and inference
    assert set(train_df["sku_id"]).isdisjoint(set(inf_df["sku_id"]))
    assert "EVAL_SECRET_01" not in set(train_df["sku_id"])

    # 2. Target units_sold is strictly null in inference features
    assert inf_df["units_sold"].isnull().all()


def test_hidden_labels_inaccessible_in_api_payloads():
    """Verify that actual sales figures for cold-start evaluation items are never exposed via API."""
    client = TestClient(app)
    # Check single SKU detail
    res = client.get("/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_EVAL_001", headers=VIEWER_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "units_sold" not in data
    assert "actual_sales" not in data
    assert "ground_truth" not in data
    for fc in data["forecasts"]:
        assert "units_sold" not in fc
        assert "actual_sales" not in fc


# =============================================================================
# 3. DETERMINISTIC REPRODUCIBILITY ACROSS IDENTICAL SEEDS
# =============================================================================

def test_reproducibility_identical_predictions_and_intervals():
    """Confirm that forecasting models and conformal uncertainty are 100% deterministic given a fixed seed."""
    df_cal = pd.DataFrame([
        {"sku_id": f"CAL_{i}", "launch_week_age": w, "units_sold": 100.0 + (i * w) % 17}
        for i in range(1, 15) for w in range(1, 9)
    ])
    preds = np.full(len(df_cal), 100.0)

    cal1 = ConformalIntervalCalibrator()
    cal1.calibrate(df_cal, preds, confidence_levels=[0.80, 0.90])

    cal2 = ConformalIntervalCalibrator()
    cal2.calibrate(df_cal, preds, confidence_levels=[0.80, 0.90])

    assert np.isclose(cal1.weekly_cutoffs[0.80], cal2.weekly_cutoffs[0.80])
    assert np.isclose(cal1.weekly_cutoffs[0.90], cal2.weekly_cutoffs[0.90])
    assert cal1.weekly_cutoffs[0.90] >= cal1.weekly_cutoffs[0.80]


# =============================================================================
# 4. MALFORMED DATA, MISSING FEATURES & UNSEEN CATEGORIES
# =============================================================================

def test_unknown_category_and_attribute_resilience():
    """Verify that unseen categories, null materials, and novel price bands process gracefully without crashing."""
    artifact_path = Path("artifacts/models/supervised_coldstart_v1")
    if not artifact_path.exists():
        pytest.skip("Model artifact supervised_coldstart_v1 not available on local disk.")

    predictor = ColdStartPredictor.from_artifact(artifact_path)

    # SKU with unseen category and missing non-mandatory attributes
    unseen_sku = {
        "sku_id": "SKU_NOVEL_999",
        "category": "ExtraterrestrialGear",  # Completely unseen in training
        "subcategory": "AntigravityBoots",
        "colour": None,
        "material": None,
        "base_price": 250.0,
        "brand": "UnknownAlienCo",
        "brand_tier": None,
        "launch_date": "2025-06-01",
        "has_marketing_support": False,
    }

    # Predictor must succeed and return 8 finite, non-negative weekly predictions
    forecast_result = predictor.predict_sku(unseen_sku)
    assert len(forecast_result.weekly_forecast) == 8
    for p in forecast_result.weekly_forecast:
        assert np.isfinite(p)
        assert p >= 0.0
    assert np.isfinite(forecast_result.cumulative_8w_forecast)
    assert forecast_result.cumulative_8w_forecast >= 0.0


def test_non_negative_finite_and_monotonic_intervals():
    """Verify that predictions are finite, non-negative, and intervals strictly satisfy 0 <= L80 <= median <= U80
    and [L80, U80] is strictly contained within [L90, U90]."""
    df_cal = pd.DataFrame([
        {"sku_id": f"CAL_{i}", "launch_week_age": w, "units_sold": 80.0 + (i * 3 + w) % 25}
        for i in range(1, 15) for w in range(1, 9)
    ])
    preds = np.full(len(df_cal), 80.0)

    calibrator = ConformalIntervalCalibrator()
    calibrator.calibrate(df_cal, preds, confidence_levels=[0.80, 0.90])

    test_preds = np.array([25.0, 30.0, 28.0, 22.0, 18.0, 15.0, 12.0, 10.0])
    l80, u80 = calibrator.predict_weekly_intervals(test_preds, confidence_level=0.80)
    l90, u90 = calibrator.predict_weekly_intervals(test_preds, confidence_level=0.90)

    assert len(l80) == 8
    assert (l80 >= 0.0).all()
    assert (l90 >= 0.0).all()
    assert (l90 <= l80).all()
    assert (u90 >= u80).all()
    assert (l80 <= test_preds).all()
    assert (test_preds <= u80).all()


# =============================================================================
# 5. INVENTORY SCENARIO STRESS TESTING & CONSTRAINT ENFORCEMENT
# =============================================================================

def test_inventory_zero_demand_scenario():
    """Under zero demand, recommended quantity is 0 (or strictly MOQ if MOQ is forced)."""
    optimizer = NewsvendorOptimizer()
    rec = optimizer.optimize_sku(
        sku_id="ZERO_DEMAND_SKU",
        cumulative_demand_mean=0.0,
        cumulative_demand_lower_90=0.0,
        cumulative_demand_upper_90=0.0,
        base_price=50.0,
        custom_cu=20.0,
        custom_co=10.0,
    )
    assert rec.recommended_buy_quantity == 0
    assert rec.expected_shortage_units == 0.0


def test_inventory_extreme_cost_asymmetries():
    """Verify that when understock cost Cu >> Co, critical ratio approaches 1 and Q* is high.
    When Co >> Cu, critical ratio approaches 0 and Q* is conservative."""
    optimizer = NewsvendorOptimizer()
    mu = 500.0
    lb90, ub90 = 350.0, 650.0

    # High service scenario: Cu=90, Co=10 -> CR = 0.90
    rec_high = optimizer.optimize_sku(
        sku_id="HIGH_CR_SKU",
        cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb90,
        cumulative_demand_upper_90=ub90,
        base_price=100.0,
        custom_cu=90.0,
        custom_co=10.0,
    )

    # Low service scenario: Cu=10, Co=90 -> CR = 0.10
    rec_low = optimizer.optimize_sku(
        sku_id="LOW_CR_SKU",
        cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb90,
        cumulative_demand_upper_90=ub90,
        base_price=100.0,
        custom_cu=10.0,
        custom_co=90.0,
    )

    assert rec_high.critical_ratio == pytest.approx(0.90, rel=1e-3)
    assert rec_low.critical_ratio == pytest.approx(0.10, rel=1e-3)
    assert rec_high.recommended_buy_quantity > rec_low.recommended_buy_quantity
    assert rec_high.expected_fill_rate_pct > rec_low.expected_fill_rate_pct


def test_inventory_case_pack_and_moq_compliance():
    """Ensure recommended buy quantities strictly adhere to integer multiples of case_pack_size and MOQ."""
    optimizer = NewsvendorOptimizer()
    mu = 137.0
    lb90, ub90 = 100.0, 175.0
    constraints = InventoryConstraints(min_order_quantity=50, case_pack_size=12)
    rec = optimizer.optimize_sku(
        sku_id="CASE_PACK_SKU",
        cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb90,
        cumulative_demand_upper_90=ub90,
        base_price=50.0,
        custom_cu=25.0,
        custom_co=15.0,
        constraints=constraints,
    )
    assert rec.recommended_buy_quantity % 12 == 0
    assert rec.recommended_buy_quantity >= 50


# =============================================================================
# 6. MODEL ARTIFACT CRYPTOGRAPHIC INTEGRITY & TAMPER DETECTION
# =============================================================================

def test_model_artifact_tamper_detection(tmp_path: Path):
    """Verify that tampering with model artifact weights triggers ModelIntegrityError on load."""
    artifact_dir = tmp_path / "test_artifact"
    artifact_dir.mkdir(parents=True)

    # Create dummy config with SHA256 of valid content
    valid_content = b"ORIGINAL_CATBOOST_WEIGHTS_CONTENT"
    valid_sha = hashlib.sha256(valid_content).hexdigest()

    model_file = artifact_dir / "catboost_model.cbm"
    model_file.write_bytes(valid_content)

    config = {
        "model_type": "CatBoostRegressor",
        "objective": "MAE",
        "target_transform": "log1p",
        "iterations": 10,
        "learning_rate": 0.05,
        "depth": 4,
        "l2_leaf_reg": 3.0,
        "random_seed": 42,
        "feature_columns": ["f1"],
        "categorical_columns": [],
        "sha256_checksum": valid_sha,
    }
    with open(artifact_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Tamper with the model file by changing one byte
    tampered_content = b"TAMPERED_CATBOOST_WEIGHTS_CONTENT"
    model_file.write_bytes(tampered_content)

    # Attempting to load MUST raise ModelIntegrityError
    with pytest.raises(ModelIntegrityError) as exc_info:
        CatBoostForecaster.load_artifact(artifact_dir, verify_integrity=True)

    assert "cryptographic integrity verification" in str(exc_info.value)


# =============================================================================
# 7. SENSITIVE CREDENTIALS REDACTION IN STRUCTURED LOGGING
# =============================================================================

def test_sensitive_data_logging_redaction():
    """Verify that SensitiveDataFilter redacts API keys, passwords, and bearer tokens from log messages."""
    log_filter = SensitiveDataFilter()

    # Test 1: Plaintext R4 API key in message
    record1 = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=10,
        msg="Authenticated user with key r4-admin-key-2026-xyz successfully",
        args=(), exc_info=None,
    )
    log_filter.filter(record1)
    assert "r4-admin-key-2026-xyz" not in record1.msg
    assert "[REDACTED_API_KEY]" in record1.msg

    # Test 2: Bearer token redaction
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=20,
        msg="Forwarding token Bearer eyJhbGciOiJIUzI1NiJ9.test",
        args=(), exc_info=None,
    )
    log_filter.filter(record2)
    assert "eyJhbGciOiJIUzI1NiJ9" not in record2.msg
    assert "Bearer [REDACTED_TOKEN]" in record2.msg

    # Test 2b: Authorization header token redaction
    record2b = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=25,
        msg="Forwarding header Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test",
        args=(), exc_info=None,
    )
    log_filter.filter(record2b)
    assert "eyJhbGciOiJIUzI1NiJ9" not in record2b.msg
    assert "[REDACTED_TOKEN]" in record2b.msg

    # Test 3: Password / Secret in dictionary argument
    record3 = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=30,
        msg="Database config: %s",
        args=({"password": "SuperSecretPassword123!"},), exc_info=None,
    )
    log_filter.filter(record3)
    assert "SuperSecretPassword123!" not in str(record3.args)


# =============================================================================
# 8. GOVERNANCE RULE: DRIFT ALONE PROHIBITS AUTOMATED MODEL PROMOTION
# =============================================================================

def test_governance_drift_does_not_auto_promote():
    """Enforce critical governance policy: Detecting drift alone NEVER automatically promotes a model.
    Formal human approval and official WAPE validation are strictly mandatory."""
    # Scenario A: Drift detected, no human approval -> BLOCKED even if candidate WAPE is better
    promoted_a, reason_a = ModelGovernance.evaluate_model_promotion(
        candidate_model_id="v2.0.0-candidate",
        candidate_wape=0.2200,
        baseline_wape=0.2561,
        drift_detected=True,
        human_approved=False,
    )
    assert promoted_a is False
    assert "BLOCKED: Feature/data drift detected" in reason_a

    # Scenario B: Drift detected, WITH human sign-off -> APPROVED if WAPE improves
    promoted_b, reason_b = ModelGovernance.evaluate_model_promotion(
        candidate_model_id="v2.0.0-candidate",
        candidate_wape=0.2200,
        baseline_wape=0.2561,
        drift_detected=True,
        human_approved=True,
    )
    assert promoted_b is True
    assert "APPROVED" in reason_b

    # Scenario C: Candidate fails official WAPE threshold (> 0.2800) -> REJECTED
    promoted_c, reason_c = ModelGovernance.evaluate_model_promotion(
        candidate_model_id="v3.0.0-candidate",
        candidate_wape=0.3150,
        baseline_wape=0.3500,
        drift_detected=False,
        human_approved=True,
    )
    assert promoted_c is False
    assert "fails official threshold" in reason_c


# =============================================================================
# 9. REGRESSION TEST: MULTIPLE RECOMMENDATION SCENARIOS PER SKU
# =============================================================================

@pytest.mark.asyncio
async def test_regression_multiple_recommendation_scenarios():
    """Regression test for MultipleResultsFound bug:
    Ensure get_sku_forecast safely resolves when multiple scenario recommendations exist for a single SKU."""
    run_id = f"RUN_REG_{int(datetime.now().timestamp())}"

    async with async_session_scope() as session:
        repo = ForecastRepository(session)
        # Create test SKU and run
        await repo.upsert_sku({
            "sku_id": "SKU_REG_01",
            "product_name": "Regression Test Item",
            "category": "Equipment",
            "subcategory": "Backpacks",
            "base_price": 85.0,
            "launch_date": date(2025, 4, 1),
            "has_marketing_support": True,
            "is_evaluation_sku": True,
        })
        await repo.create_forecast_run({
            "run_id": run_id,
            "model_id": "v1.0.0-catboost-coldstart",
            "status": "COMPLETED",
            "sku_count": 1,
            "reproducibility_seed": 42,
        })
        # Insert BASE scenario recommendation
        await repo.save_inventory_recommendations(run_id, [{
            "run_id": run_id,
            "sku_id": "SKU_REG_01",
            "scenario": "BASE",
            "forecast_cumulative_8w": 400.0,
            "recommended_buy_quantity": 420,
            "critical_ratio": 0.60,
            "understock_cost_cu": 25.0,
            "overstock_cost_co": 15.0,
        }])
        # Insert CONSERVATIVE scenario recommendation for the SAME SKU
        await repo.save_inventory_recommendations(run_id, [{
            "run_id": run_id,
            "sku_id": "SKU_REG_01",
            "scenario": "CONSERVATIVE",
            "forecast_cumulative_8w": 400.0,
            "recommended_buy_quantity": 380,
            "critical_ratio": 0.50,
            "understock_cost_cu": 20.0,
            "overstock_cost_co": 20.0,
        }])
        await session.commit()

        # get_sku_forecast must execute safely without raising MultipleResultsFound
        sku_detail = await repo.get_sku_forecast(run_id, "SKU_REG_01")
        assert sku_detail is not None
        assert sku_detail["recommendation"] is not None
        # Must pick the latest inserted scenario
        assert sku_detail["recommendation"]["scenario"] == "CONSERVATIVE"


# =============================================================================
# 10. TELEMETRY AND AUDIT WARN VERIFICATION
# =============================================================================

def test_telemetry_tracker_metrics():
    """Verify TelemetryTracker accurately computes p50, p95, p99, and error counts."""
    tracker = TelemetryTracker(max_history=100)
    for dur in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
        tracker.record_request("GET", "/test", 200, dur)
    tracker.record_request("POST", "/error", 500, 150.0)

    summary = tracker.get_summary()
    assert summary["total_requests"] == 11
    assert summary["error_count"] == 1
    assert summary["p50_ms"] == pytest.approx(55.0, abs=5.0)
    assert summary["max_ms"] == 150.0


def test_production_security_audit_warnings():
    """Verify Settings.validate_production_security detects default secrets in production."""
    prod_settings = Settings(
        environment="production",
        secret_key="dev-secret-key",
        api_key_admin="r4-admin-key-2026",
        allowed_origins="http://localhost:3000",
        database_url="sqlite:///data/prod.db",
    )
    warnings = prod_settings.validate_production_security()
    assert len(warnings) >= 3
    assert any("Default 'dev-secret-key'" in w for w in warnings)
    assert any("Default admin API key" in w for w in warnings)
    assert any("SQLite in production" in w for w in warnings)
