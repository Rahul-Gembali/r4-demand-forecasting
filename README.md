# R4 New Product Demand Forecasting Platform

[![GitHub repository](https://img.shields.io/badge/GitHub-Rahul--Gembali%2Fr4--demand--forecasting-blue?logo=github)](https://github.com/Rahul-Gembali/r4-demand-forecasting)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.14-blue.svg?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg?logo=react)](https://react.dev/)
[![Tests](https://img.shields.io/badge/Tests-104%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An enterprise machine-learning system for cold-start demand forecasting of 150 newly introduced retail SKUs over their introductory 8-week lifecycle ($W_1$ through $W_8$) across store clusters and holiday variations.

```
       ┌────────────────────────┐
       │ Raw Catalog Ingestion  │
       └───────────┬────────────┘
                   ▼
       ┌────────────────────────┐
       │ Data Pipeline & Preproc│
       └───────────┬────────────┘
                   ▼
    ┌──────────────┴──────────────┐
    ▼                             ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│ Category Launch Curves  │  │ Gower Analogue Engine   │
└───────────┬─────────────┘  └────────────┬────────────┘
            └──────────────┬──────────────┘
                           ▼
              ┌────────────────────────┐
              │ Supervised CatBoost    │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │ Split Conformal 80/90% │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │ Single-Period Newsvendor│
              │ Buy Optimization (MOQ) │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │ PostgreSQL Persistence │
              │ Alembic Versioning     │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │ FastAPI REST Gateway   │
              │ RBAC & Telemetry       │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │ React + TS Dashboard   │
              │ 7 Operational Screens  │
              └────────────────────────┘
```

---

## 1. System Overview

- **Cold-Start Challenge:** Predicting weekly unit demand for 150 newly introduced retail SKUs that have zero historical transaction records.
- **Historical Transfer Pool:** Leveraging attribute embeddings and launch curve trajectories from ~1,200 mature or discontinued reference SKUs.
- **Forecasting Engine:** Pooled CatBoost gradient boosted decision trees predicting log-transformed weekly unit sales conditioned on launch age and product attributes.
- **Uncertainty Calibration:** Split conformal residual prediction yielding calibrated 80% and 90% weekly and cumulative prediction bounds ($0 \le L_{90} \le L_{80} \le \hat{y} \le U_{80} \le U_{90}$).
- **Inventory Optimization:** Single-period Newsvendor optimizer computing critical ratio $Cu / (Cu + Co)$ and optimal buy quantity subject to supplier MOQ and case-pack rounding.
- **Explainability:** Exact TreeSHAP feature attributions, analogue similarity evidence, and automated confidence scoring with tiering.
- **Backend & Database:** FastAPI asynchronous REST API with RBAC (`admin`, `operator`, `viewer`), Alembic migrations, and PostgreSQL persistence.
- **Frontend Dashboard:** Production React 18 + TypeScript + Vite operations dashboard featuring 7 dedicated operational screens.
- **Security & Reliability:** Zero evaluation SKU target leakage, cryptographic model SHA-256 integrity verification, automated log redaction, and strict drift governance.

---

## 2. Directory Structure

```
r4-demand-forecasting/
├── artifacts/models/              # Serialized CatBoost models, configs, manifests
├── data/
│   ├── raw/                       # Immutable raw catalog CSVs
│   ├── interim/                   # Cleaned and harmonized datasets
│   └── processed/                 # Training features, forecasts, recommendations
├── frontend/                      # React 18 + TypeScript + Vite Dashboard
│   ├── src/                       # Components, screens, API clients, theme
│   ├── Dockerfile                 # Multi-stage production build (Node + Nginx)
│   └── nginx.conf                 # SPA routing and API reverse proxy
├── migrations/                    # Alembic schema migrations
├── scripts/                       # MLOps pipeline scripts and verification tools
│   ├── init_db.py                 # Idempotent DB schema init and safe seeding
│   ├── run_pipeline.py            # Feature engineering pipeline
│   ├── run_phase3_baselines.py    # Category curves & analogue retrieval
│   ├── train_supervised.py        # Supervised CatBoost model training
│   ├── evaluate_uncertainty.py    # Conformal calibration & metrics
│   ├── optimize_inventory.py      # Newsvendor buy quantity optimization
│   ├── generate_explanations.py   # TreeSHAP & confidence rankings
│   └── verify_api_live.py         # End-to-end live API verification
├── src/
│   ├── api/                       # FastAPI routes, schemas, auth, middleware
│   ├── core/                      # Config, logging, telemetry, drift monitoring
│   ├── data/                      # Ingestion, validation, feature pipeline
│   ├── db/                        # SQLAlchemy async models, repository, session
│   ├── evaluation/                # Official WAPE evaluator & conformal calibrator
│   ├── explainability/            # TreeSHAP engine, confidence scorer, synthesizer
│   ├── inventory/                 # Newsvendor cost model & constraints
│   └── models/                    # Baselines, analogue retrieval, CatBoost
├── tests/                         # 104 comprehensive Pytest test cases
├── .github/workflows/ci.yml       # GitHub Actions CI workflow
├── docker-compose.yml             # Postgres, FastAPI, React/Nginx orchestration
├── Dockerfile                     # Production FastAPI backend Dockerfile
├── DEPLOYMENT.md                  # Comprehensive deployment and operations guide
└── pyproject.toml                 # Packaging, Ruff, MyPy, and Pytest configs
```

---

## 3. Quickstart with Docker Compose

Launch the entire stack (PostgreSQL, FastAPI Backend, React Dashboard, and Worker) in one command:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Build and launch all containers
docker compose up -d --build

# 3. Verify health status
docker compose ps
```

Once running, access:
- **Web Dashboard:** `http://localhost/` or `http://localhost:3000/`
- **FastAPI OpenAPI Docs:** `http://localhost:8000/docs`
- **Health Probe:** `http://localhost:8000/health`
- **Telemetry Metrics:** `http://localhost:8000/api/v1/monitoring/telemetry`

To stop:
```bash
docker compose down
```

For complete deployment runbooks, database backup/restore, and production hardening, see [DEPLOYMENT.md](file:///E:/r4-demand-forecasting/DEPLOYMENT.md).

---

## 4. Test Suite and Quality Verification

All 104 unit, integration, and security tests execute cleanly:

```bash
# Run complete test suite (104 tests)
pytest -v

# Run code formatting and linting
ruff check src tests scripts

# Run static type analysis
mypy src/core/monitoring.py src/core/config.py src/core/logging.py

# Build frontend production bundle
cd frontend && npm run build
```

### Verification Summary
- **Pytest:** 104 passed in ~25 seconds.
- **Ruff:** 0 warnings / 0 errors.
- **MyPy:** 0 type issues across core modules.
- **Frontend Build:** 1,569 TypeScript modules compiled cleanly to `frontend/dist/`.

---

## 5. Official Evaluation Results (150 Cold-Start SKUs)

| Model / Approach | Horizon WAPE ($W_1-W_8$) | Cumulative 8W WAPE | Forecast Bias (%) | 90% Empirical Coverage |
| :--- | :---: | :---: | :---: | :---: |
| Category Launch Curve Baseline | 0.3842 | 0.3610 | +12.4% | N/A |
| Top-5 Gower Analogue Retrieval | 0.3418 | 0.3204 | +6.8% | N/A |
| **Supervised CatBoost GBDT (Selected)** | **0.2561** | **0.2314** | **-3.76%** | **89.33%** |

- **Official WAPE Target:** Achieved **0.2561**, surpassing the official $\le 0.2800$ target threshold.
- **Confidence Ranking:** Evaluated all 150 evaluation SKUs; identified the 10 least-confident products with evidence explanations.
- **Total Initial Buy Commitment:** 222,246 units across 150 items under base Newsvendor cost assumptions.

---

## 6. License & Team
Developed for the R4 Retail Demand Forecasting Cold-Start Challenge.
Licensed under the MIT License.
