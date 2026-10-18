# R4 Demand Forecasting Backend API Documentation

Production REST API for retail cold-start demand forecasting, conformal uncertainty intervals, single-period Newsvendor inventory optimization, and TreeSHAP explainability.

---

## 1. Architecture & Security Overview

### 1.1. Base URL & OpenAPI Documentation
- **API Base URL**: `http://localhost:8000/api/v1`
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI Schema Specification**: `http://localhost:8000/openapi.json`

### 1.2. Authentication & Role-Based Access Control (RBAC)
All endpoints (except `/health` and `/ready`) require an API key passed via the `X-API-Key` header or `Authorization: Bearer <key>`.

| Role | Configured Key (Default) | Permitted Endpoints |
| :--- | :--- | :--- |
| **Admin** | `r4-admin-key-2026` | Full access (`/data/import`, `/models/train`, `/forecasts`, `/inventory/optimize`, etc.) |
| **Operator** | `r4-operator-key-2026` | Operations access (`/data/import`, `/forecasts`, `/inventory/optimize`, queries) |
| **Viewer** | `r4-viewer-key-2026` | Read-only access (`/models`, `/forecasts/{id}`, `/reports/{id}`, `/jobs/{id}`) |

### 1.3. Standardized Error Envelope
All error responses adhere to the standard envelope:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request payload failed schema validation.",
    "request_id": "req_358230768614",
    "details": {
      "validation_errors": [
        {"field": "body -> iterations", "issue": "Input should be greater than or equal to 10"}
      ]
    }
  }
}
```

---

## 2. Server Startup Commands

```bash
# Option 1: Standard entry point
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Option 2: Project entry point script
r4-serve
```

---

## 3. Complete Endpoints Reference

### 3.1. Health & Readiness Probes

#### `GET /health` (or `/api/v1/health`)
Liveness check returning service health.
```bash
curl -X GET "http://localhost:8000/health"
```
**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "r4-demand-forecasting",
  "version": "0.1.0",
  "timestamp": "2026-10-18T14:18:09.073974Z"
}
```

#### `GET /ready` (or `/api/v1/ready`)
Readiness check validating database connection, model weights availability, and filesystem storage.
```bash
curl -X GET "http://localhost:8000/ready"
```
**Response (200 OK):**
```json
{
  "ready": true,
  "components": {
    "database": {"status": "UP", "details": "Database connection active and responsive."},
    "model_registry": {"status": "UP", "details": "Model artifact present (172.8 KB)."},
    "storage": {"status": "UP", "details": "Data filesystem paths accessible."}
  },
  "timestamp": "2026-10-18T14:18:09.089754+00:00"
}
```

---

### 3.2. Data Ingestion (`POST /api/v1/data/import`)
Upload candidate SKU attributes or reference data (.csv, .parquet, .xlsx). Restricts file size to 50MB and prevents path traversal.

```bash
curl -X POST "http://localhost:8000/api/v1/data/import" \
  -H "X-API-Key: r4-operator-key-2026" \
  -F "file=@new_sku_attributes.csv" \
  -F "manifest_type=NEW_SKUS" \
  -F "is_evaluation_data=true"
```
**Response (201 Created):**
```json
{
  "filename": "new_sku_attributes.csv",
  "manifest_type": "NEW_SKUS",
  "rows_parsed": 150,
  "skus_upserted": 150,
  "sha256_checksum": "5c9e4726bfad...",
  "is_evaluation_data": true,
  "warnings": []
}
```

---

### 3.3. Model Registry & Asynchronous Training

#### `POST /api/v1/models/train`
Dispatches an asynchronous training job for CatBoost or LightGBM models.
```bash
curl -X POST "http://localhost:8000/api/v1/models/train" \
  -H "X-API-Key: r4-admin-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "algorithm": "CatBoostRegressor",
    "objective": "MAE",
    "target_transform": "log1p",
    "iterations": 300,
    "learning_rate": 0.03,
    "depth": 6,
    "l2_leaf_reg": 3.0,
    "random_seed": 42
  }'
```
**Response (202 Accepted):**
```json
{
  "job_id": "JOB_A1B2C3D4E5F6",
  "job_type": "MODEL_TRAINING",
  "status": "RUNNING",
  "progress_pct": 10.0,
  "created_at": "2026-10-18T14:15:00Z",
  "completed_at": null,
  "result": null,
  "error": null
}
```

#### `GET /api/v1/jobs/{job_id}`
Poll execution status and progress of an asynchronous task.
```bash
curl -X GET "http://localhost:8000/api/v1/jobs/JOB_A1B2C3D4E5F6" \
  -H "X-API-Key: r4-viewer-key-2026"
```

#### `GET /api/v1/models`
Retrieve all registered model versions from the database.
```bash
curl -X GET "http://localhost:8000/api/v1/models" \
  -H "X-API-Key: r4-viewer-key-2026"
```
**Response (200 OK):**
```json
{
  "models": [
    {
      "model_id": "v1.0.0-catboost-coldstart",
      "algorithm": "CatBoostRegressor",
      "objective": "MAE",
      "target_transform": "log1p",
      "artifact_path": "artifacts/models/supervised_coldstart_v1/catboost_model.cbm",
      "validation_wape": 0.2561,
      "created_at": "2026-10-18T13:59:16Z"
    }
  ],
  "total": 1
}
```

---

### 3.4. Forecasting & Prediction Endpoints

#### `POST /api/v1/forecasts`
Trigger batch forecast generation (synchronous or asynchronous).
```bash
curl -X POST "http://localhost:8000/api/v1/forecasts" \
  -H "X-API-Key: r4-operator-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "RUN_BATCH_2026_01",
    "async_mode": false
  }'
```
**Response (201 Created):**
```json
{
  "run_id": "RUN_BATCH_2026_01",
  "model_id": "v1.0.0-catboost-coldstart",
  "status": "COMPLETED",
  "sku_count": 150,
  "created_at": "2026-10-18T14:18:00Z",
  "completed_at": "2026-10-18T14:18:05Z",
  "overall_wape": 0.2561,
  "overall_bias_pct": -3.76,
  "total_recommended_buy_units": 117162,
  "total_expected_cost": 474664.20,
  "average_confidence_score": 77.51,
  "average_fill_rate_pct": 96.69
}
```

#### `GET /api/v1/forecasts/{run_id}`
Retrieve executive run summary and portfolio inventory totals.
```bash
curl -X GET "http://localhost:8000/api/v1/forecasts/RUN_EVAL_150_V1" \
  -H "X-API-Key: r4-viewer-key-2026"
```

#### `GET /api/v1/forecasts/{run_id}/skus/{sku_id}`
Retrieve complete SKU-level forecast, conformal bounds, analogues, and inventory recommendation.
```bash
curl -X GET "http://localhost:8000/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_EVAL_001" \
  -H "X-API-Key: r4-viewer-key-2026"
```
**Response (200 OK):**
```json
{
  "sku_id": "SKU_EVAL_001",
  "product_name": "ValueCraft New Sneakers Grey",
  "category": "Footwear",
  "subcategory": "Sneakers",
  "colour": "Grey",
  "material": "Synthetic",
  "base_price": 104.60,
  "brand": "ValueCraft",
  "brand_tier": "Tier 3 Value",
  "launch_date": "2025-01-01",
  "has_marketing_support": false,
  "is_evaluation_sku": true,
  "forecasts": [
    {
      "horizon_week": 1,
      "predicted_sales": 80.63,
      "lower_bound_80": 46.05,
      "upper_bound_80": 115.21,
      "lower_bound_90": 36.68,
      "upper_bound_90": 124.58
    }
  ],
  "recommendation": {
    "scenario": "BASE",
    "forecast_cumulative_8w": 501.40,
    "recommended_buy_quantity": 522,
    "critical_ratio": 0.6286,
    "understock_cost_cu": 47.07,
    "overstock_cost_co": 36.61,
    "expected_total_cost": 2360.76,
    "expected_fill_rate_pct": 96.38,
    "confidence_score": 84.03,
    "confidence_tier": "HIGH"
  },
  "analogues": [
    {
      "rank": 1,
      "analogue_sku_id": "SKU_HIST_0417",
      "similarity_score": 0.8982,
      "observed_curve": [45.0, 78.0, 94.0, 39.0, 50.0, 34.0, 56.0, 56.0]
    }
  ]
}
```

#### `GET /api/v1/forecasts/{run_id}/low-confidence`
Retrieve products sorted by lowest Cold-Start Confidence Index for manual merchant review.
```bash
curl -X GET "http://localhost:8000/api/v1/forecasts/RUN_EVAL_150_V1/low-confidence?limit=3" \
  -H "X-API-Key: r4-viewer-key-2026"
```
**Response (200 OK):**
```json
{
  "run_id": "RUN_EVAL_150_V1",
  "count": 3,
  "items": [
    {
      "sku_id": "SKU_EVAL_120",
      "product_name": "Zenith New Jackets Olive",
      "category": "Apparel",
      "subcategory": "Jackets",
      "base_price": 189.50,
      "confidence_score": 46.2,
      "confidence_tier": "LOW",
      "forecast_cumulative_8w": 589.2,
      "recommended_buy_quantity": 618,
      "explanation_summary": "Elevated uncertainty due to wide conformal intervals and high price band."
    }
  ]
}
```

---

### 3.5. Inventory Optimization (`POST /api/v1/inventory/optimize`)
Execute customized single-period Newsvendor scenarios with user-defined cost parameters and packaging constraints.

```bash
curl -X POST "http://localhost:8000/api/v1/inventory/optimize" \
  -H "X-API-Key: r4-operator-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "RUN_EVAL_150_V1",
    "scenario_name": "CONSERVATIVE_MARKDOWN",
    "understock_cost_cu": 20.0,
    "overstock_cost_co": 40.0,
    "min_order_quantity": 50,
    "case_pack_size": 12
  }'
```
**Response (200 OK):**
```json
{
  "run_id": "RUN_EVAL_150_V1",
  "scenario_name": "CONSERVATIVE_MARKDOWN",
  "total_skus_optimized": 150,
  "total_buy_units": 105084,
  "total_expected_cost": 521400.12,
  "average_fill_rate_pct": 90.1,
  "recommendations": [
    {
      "sku_id": "SKU_EVAL_001",
      "scenario": "CONSERVATIVE_MARKDOWN",
      "recommended_buy_quantity": 480,
      "critical_ratio": 0.3333,
      "expected_total_cost": 2528.12,
      "expected_fill_rate_pct": 92.15
    }
  ]
}
```

---

### 3.6. Executive Evaluation Report (`GET /api/v1/reports/{run_id}`)
Retrieve official evaluation metrics, empirical conformal interval coverages, inventory commitments, and cryptographic data manifests.

```bash
curl -X GET "http://localhost:8000/api/v1/reports/RUN_EVAL_150_V1" \
  -H "X-API-Key: r4-viewer-key-2026"
```
**Response (200 OK):**
```json
{
  "run_id": "RUN_EVAL_150_V1",
  "model_id": "v1.0.0-catboost-coldstart",
  "status": "COMPLETED",
  "created_at": "2026-10-18T13:59:16Z",
  "completed_at": "2026-10-18T13:59:16Z",
  "portfolio_metrics": {
    "sku_count": 150,
    "overall_wape": 0.2561,
    "overall_bias_pct": -3.76,
    "reproducibility_seed": 42
  },
  "uncertainty_calibration": {
    "conformal_method": "split_conformal_residual_quantile",
    "target_coverage_80": 0.80,
    "empirical_coverage_80": 0.8037,
    "target_coverage_90": 0.90,
    "empirical_coverage_90": 0.9075,
    "cumulative_interval_efficiency": "60.3% tighter than naive weekly interval summing"
  },
  "inventory_summary": {
    "total_recommended_buy_units": 117162,
    "total_expected_cost": 474664.20,
    "average_confidence_score": 77.51,
    "average_fill_rate_pct": 96.69
  },
  "least_confident_skus_summary": [
    {"sku_id": "SKU_EVAL_120", "confidence_score": 46.2, "confidence_tier": "LOW"}
  ],
  "data_manifests": [
    {"manifest_type": "PROCESSED_INTERVALS", "sha256_checksum": "a1b2c3d4..."}
  ]
}
```
