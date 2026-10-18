# R4 New Product Demand Forecasting

An enterprise machine-learning system for cold-start demand forecasting of 150 new retail SKUs over their introductory 8-week lifecycle ($W_1$ through $W_8$) across store clusters and holiday variations.

---

## 1. Problem Overview
- **Cold-Start Challenge**: Predicting weekly unit demand for 150 newly launched products that have zero historical transaction records.
- **Historical Transfer Pool**: Leveraging attribute embeddings and launch curve trajectories from ~1,200 mature or discontinued reference SKUs.
- **Evaluation Criteria**: Weighted Absolute Percentage Error (WAPE), RMSE, MAE, and aggregate Forecast Bias.
- **Security & Leakage Constraint**: Strict isolation of evaluation ground-truth labels.

---

## 2. Project Directory Structure
```
r4-demand-forecasting/
├── docs/                      # Architectural & Data specifications
│   ├── ARCHITECTURE.md        # Modular Monolith system architecture
│   ├── DATA_AUDIT.md          # Filesystem scan & Phase 1 audit report
│   ├── DATA_DICTIONARY.md     # Target schema & cold-start nuances
│   └── EVALUATION_SPEC.md     # Official metric definitions & constraints
├── data/
│   ├── raw/                   # Immutable raw landing directory (CSV/Parquet)
│   ├── interim/               # Harmonized tables and typed views
│   └── processed/             # Cold-start feature store & similarity sets
├── src/
│   ├── api/                   # FastAPI REST gateway and route definitions
│   ├── core/                  # Configuration, logging, and database engine
│   ├── data/                  # Schema inspector and data loaders
│   ├── evaluation/            # Vectorized metrics & evaluation runner
│   └── models/                # Cold-start similarity & multi-horizon estimators
├── frontend/                  # React 18 + TypeScript + Vite operations UI
├── scripts/
│   └── inspect_data.py        # Automated schema & data discovery CLI tool
├── tests/                     # Pytest suite (metrics, inspector, API)
├── pyproject.toml             # Python packaging, ruff, mypy, pytest configs
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development & test dependencies
├── .env.example               # Environment variables template
└── .gitignore                 # Exclusion rules
```

---

## 3. Quick Start & Setup

### Python Environment Setup
```bash
# Recommended Python version: 3.12+
python -m venv .venv
# Activate on Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### Running the Data Discovery Inspection
```bash
# Audit raw datasets and compile schema audit ledger
python scripts/inspect_data.py --data-dir data/raw --output docs/data_audit_results.json
```

### Running the Test Suite
```bash
# Execute unit tests
python -m pytest tests/ -v
```

### Starting the FastAPI Service
```bash
# Launch development server
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Phase 1 Audit & Current Blockers
- **BLK-001**: Raw datasets (`sales`, `attributes`, `clusters`, `calendar`) are pending ingestion into `data/raw/`.
- **BLK-002**: Official benchmark script `evaluate.py` has not been provided; reference mathematical metrics are fully implemented and verified in `src/evaluation/metrics.py`.

See `docs/DATA_AUDIT.md` for full filesystem scan results.
