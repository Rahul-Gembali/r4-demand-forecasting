# PostgreSQL Relational Data Model & Persistence Architecture

## 1. Executive Summary & Architecture Overview

The **R4 New Product Demand Forecasting Platform** utilizes a normalized relational data model managed by **SQLAlchemy 2.0** and versioned via **Alembic**. The storage architecture supports:
- **Production Target**: PostgreSQL 16+ with native `JSONB` support, connection pooling via `AsyncAdaptedQueuePool` (async) and `QueuePool` (sync), and async I/O powered by `asyncpg`.
- **Development & CI**: Zero-dependency SQLite / `aiosqlite` with dialect variants (`JSON().with_variant(JSONB, "postgresql")` and `BigInteger().with_variant(Integer, "sqlite")`).
- **Strict Data Fencing**: Zero evaluation actual sales are permitted to enter database transaction paths; evaluation ground-truth labels remain strictly fenced in cold offline file storage.

---

## 2. Entity-Relationship Diagram (Mermaid)

```mermaid
erDiagram
    SKUS ||--o{ WEEKLY_SALES : "generates"
    STORE_CLUSTERS ||--o{ WEEKLY_SALES : "observes"
    SKUS ||--o{ WEEKLY_FORECASTS : "forecasted_in"
    SKUS ||--o{ ANALOGUE_MATCHES : "queried_in"
    SKUS ||--o{ INVENTORY_RECOMMENDATIONS : "recommended_in"
    
    MODEL_VERSIONS ||--o{ FORECAST_RUNS : "trains"
    FORECAST_RUNS ||--o{ WEEKLY_FORECASTS : "contains"
    FORECAST_RUNS ||--o{ ANALOGUE_MATCHES : "produces"
    FORECAST_RUNS ||--o{ INVENTORY_RECOMMENDATIONS : "generates"
    
    INVENTORY_RECOMMENDATIONS ||--o{ CLUSTER_ALLOCATIONS : "allocates"
    STORE_CLUSTERS ||--o{ CLUSTER_ALLOCATIONS : "receives"

    SKUS {
        varchar sku_id PK
        varchar product_name
        varchar category
        varchar subcategory
        varchar colour
        varchar material
        numeric base_price
        varchar brand
        varchar brand_tier
        date launch_date
        boolean has_marketing_support
        boolean is_evaluation_sku
        timestamptz created_at
    }

    STORE_CLUSTERS {
        varchar cluster_id PK
        varchar cluster_name
        text description
        integer store_count
        varchar regional_climate
        varchar income_tier
        timestamptz created_at
    }

    HOLIDAYS {
        bigint id PK
        varchar holiday_name
        date holiday_date
        integer week_of_year
        integer year
        boolean is_promotional
    }

    WEEKLY_SALES {
        bigint id PK
        varchar sku_id FK
        varchar store_id
        varchar cluster_id FK
        integer launch_week_age
        numeric units_sold
        date week_end_date
        timestamptz created_at
    }

    MODEL_VERSIONS {
        varchar model_id PK
        varchar algorithm
        varchar objective
        varchar target_transform
        varchar artifact_path
        varchar training_manifest_sha256
        numeric validation_wape
        jsonb hyperparameters
        jsonb feature_schema
        timestamptz created_at
    }

    FORECAST_RUNS {
        varchar run_id PK
        varchar model_id FK
        varchar run_type
        varchar status
        varchar input_manifest_sha256
        integer sku_count
        numeric overall_wape
        numeric overall_bias_pct
        integer reproducibility_seed
        jsonb execution_metadata
        timestamptz created_at
        timestamptz completed_at
    }

    WEEKLY_FORECASTS {
        bigint id PK
        varchar run_id FK
        varchar sku_id FK
        integer horizon_week
        numeric predicted_sales
        numeric lower_bound_80
        numeric upper_bound_80
        numeric lower_bound_90
        numeric upper_bound_90
        timestamptz created_at
    }

    ANALOGUE_MATCHES {
        bigint id PK
        varchar run_id FK
        varchar query_sku_id FK
        varchar analogue_sku_id FK
        integer rank
        numeric similarity_score
        jsonb observed_curve
    }

    INVENTORY_RECOMMENDATIONS {
        bigint id PK
        varchar run_id FK
        varchar sku_id FK
        varchar scenario
        numeric forecast_cumulative_8w
        integer recommended_buy_quantity
        numeric unconstrained_quantity
        numeric critical_ratio
        numeric understock_cost_cu
        numeric overstock_cost_co
        numeric expected_shortage_units
        numeric expected_excess_units
        numeric expected_total_cost
        numeric expected_fill_rate_pct
        numeric confidence_score
        varchar confidence_tier
        text explanation_summary
        jsonb assumptions
        timestamptz created_at
    }

    CLUSTER_ALLOCATIONS {
        bigint id PK
        bigint recommendation_id FK
        varchar sku_id FK
        varchar cluster_id FK
        integer allocated_quantity
        numeric allocation_weight
    }

    DATA_MANIFESTS {
        bigint id PK
        varchar manifest_type
        varchar file_identifier
        varchar sha256_checksum
        integer row_count
        jsonb schema_snapshot
        timestamptz created_at
    }
```

---

## 3. Data Dictionary

### 3.1. `skus` (Master Product Catalogue)
Master catalogue for both mature historical products and new cold-start candidates.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sku_id` | `VARCHAR(64)` | No | None | **PRIMARY KEY** | Unique business SKU identifier (e.g., `SKU_EVAL_001`, `SKU_HIST_0120`). |
| `product_name` | `VARCHAR(255)` | No | None | | Human-readable title combining brand, name, and attributes. |
| `category` | `VARCHAR(64)` | No | None | **INDEX** (`ix_skus_category`) | Top-level taxonomy category (e.g., `Footwear`, `Apparel`). |
| `subcategory` | `VARCHAR(64)` | No | None | **INDEX** (`ix_skus_subcategory`) | Granular merchandise segment (e.g., `Sneakers`, `Jackets`). |
| `colour` | `VARCHAR(64)` | Yes | `NULL` | | Primary dominant colourway. |
| `material` | `VARCHAR(64)` | Yes | `NULL` | | Primary fabric or construction material. |
| `base_price` | `NUMERIC(10, 2)` | No | None | | Recommended initial retail selling price in USD. |
| `brand` | `VARCHAR(64)` | Yes | `NULL` | | Registered brand label (e.g., `Zenith`, `Luxura`). |
| `brand_tier` | `VARCHAR(64)` | Yes | `NULL` | | Strategic price/market tier (e.g., `Tier 1 Premium`, `Tier 3 Value`). |
| `launch_date` | `DATE` | No | None | | Product commercial release date (defining launch week 1). |
| `has_marketing_support`| `BOOLEAN` | No | `FALSE` | | Verified launch marketing amplification campaign flag. |
| `is_evaluation_sku` | `BOOLEAN` | No | `FALSE` | **INDEX** (`ix_skus_is_evaluation_sku`) | Security flag distinguishing cold-start evaluation items from mature baseline items. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | System insertion audit timestamp. |
| `updated_at` | `TIMESTAMPTZ` | Yes | `NULL` | On Update `now()` | Last modification audit timestamp. |

---

### 3.2. `store_clusters` (Store Clustering)
Retail distribution network classification grouping physical stores with similar volume, demographics, and regional climates.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cluster_id` | `VARCHAR(64)` | No | None | **PRIMARY KEY** | Cluster identifier (e.g., `CLUSTER_1`, `CLUSTER_2`). |
| `cluster_name` | `VARCHAR(128)` | No | None | | Descriptive cluster name (e.g., `Flagship Cluster`). |
| `description` | `TEXT` | Yes | `NULL` | | Extended notes on store network profile and store mix. |
| `store_count` | `INTEGER` | No | `1` | | Number of active retail doors mapped to this cluster. |
| `regional_climate` | `VARCHAR(64)` | Yes | `NULL` | | Climatic classification (e.g., `Temperate`, `Tropical`). |
| `income_tier` | `VARCHAR(64)` | Yes | `NULL` | | Store catchment area income classification. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | System insertion timestamp. |

---

### 3.3. `holidays` (Retail Holiday Calendar)
Promotional events, statutory holidays, and seasonal calendar markers.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate surrogate primary key. |
| `holiday_name` | `VARCHAR(128)` | No | None | | Recognized holiday or event name (e.g., `Black Friday`). |
| `holiday_date` | `DATE` | No | None | **INDEX** (`ix_holidays_holiday_date`) | Calendar occurrence date. |
| `week_of_year` | `INTEGER` | No | None | | ISO fiscal week of year (1–53). |
| `year` | `INTEGER` | No | None | | Calendar year. |
| `is_promotional` | `BOOLEAN` | No | `FALSE` | | Designates major high-lift promotional discount windows. |

- **Table Constraints**:
  - `uq_holiday_name_date`: `UNIQUE(holiday_name, holiday_date)`

---

### 3.4. `weekly_sales` (Historical Realized Demand)
Granular POS sales observations across historical mature SKUs, aligned to launch-age weeks.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate primary key. |
| `sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Referenced historical product identifier. |
| `store_id` | `VARCHAR(64)` | No | None | | Physical retail store code. |
| `cluster_id` | `VARCHAR(64)` | No | None | **FK** (`store_clusters.cluster_id`) | Store cluster foreign key. |
| `launch_week_age`| `INTEGER` | No | None | | Normalized weeks elapsed since commercial launch (1–8). |
| `units_sold` | `NUMERIC(12, 2)` | No | None | | Realized units sold during the designated week. |
| `week_end_date` | `DATE` | Yes | `NULL` | | Calendar end of sales week. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Ingestion timestamp. |

- **Table Constraints & Indices**:
  - `uq_weekly_sales_sku_store_week`: `UNIQUE(sku_id, store_id, launch_week_age)`
  - `ix_sales_sku_week`: `INDEX(sku_id, launch_week_age)`
  - `ix_weekly_sales_cluster_id`: `INDEX(cluster_id)`

---

### 3.5. `model_versions` (Forecasting Model Registry)
Trained forecasting models, objective loss formulations, hyperparameter configurations, and validation benchmarks.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `model_id` | `VARCHAR(64)` | No | None | **PRIMARY KEY** | Unique model identifier (e.g., `v1.0.0-catboost-coldstart`). |
| `algorithm` | `VARCHAR(64)` | No | None | | Algorithm family (e.g., `CatBoostRegressor`, `LightGBM`). |
| `objective` | `VARCHAR(64)` | No | None | | Loss objective (e.g., `MAE`, `L1`, `MAPE`). |
| `target_transform` | `VARCHAR(32)` | No | None | | Target scaling (e.g., `log1p`, `none`). |
| `artifact_path` | `VARCHAR(512)` | No | None | | File system path to frozen binary model artifact. |
| `training_manifest_sha256` | `VARCHAR(64)` | Yes | `NULL` | | Cryptographic SHA256 hash of training data manifest. |
| `validation_wape` | `NUMERIC(8, 4)` | Yes | `NULL` | | Validation set WAPE achieved during Phase 4 model selection. |
| `hyperparameters` | `JSONB` | Yes | `NULL` | | Complete serialized hyperparameter map. |
| `feature_schema` | `JSONB` | Yes | `NULL` | | List of categorical and numerical features consumed. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Model registration timestamp. |

---

### 3.6. `forecast_runs` (Batch Execution Lineage)
Execution header tracking forecast generations, input data provenance, and completion states.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run_id` | `VARCHAR(64)` | No | None | **PRIMARY KEY** | Unique batch execution code (e.g., `RUN_EVAL_150_V1`). |
| `model_id` | `VARCHAR(64)` | No | None | **FK** (`model_versions.model_id`) | Model version utilized for this run. |
| `run_type` | `VARCHAR(32)` | No | `'EVALUATION_150'` | | Execution scope (e.g., `EVALUATION_150`, `BATCH_INFERENCE`). |
| `status` | `VARCHAR(32)` | No | `'PENDING'` | **INDEX** (`ix_forecast_runs_status`) | Execution lifecycle status (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`). |
| `input_manifest_sha256` | `VARCHAR(64)` | Yes | `NULL` | | Cryptographic SHA256 hash of input inference features. |
| `sku_count` | `INTEGER` | No | `0` | | Total number of candidate SKUs forecasted. |
| `overall_wape` | `NUMERIC(8, 4)` | Yes | `NULL` | | Overall portfolio evaluation or validation WAPE. |
| `overall_bias_pct` | `NUMERIC(8, 4)` | Yes | `NULL` | | Overall percentage bias (+ indicates overforecast, - indicates underforecast). |
| `reproducibility_seed` | `INTEGER` | No | `42` | | Global pseudorandom seed. |
| `execution_metadata` | `JSONB` | Yes | `NULL` | | Runtime environment, calibration parameters, and timing logs. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Run creation timestamp. |
| `completed_at` | `TIMESTAMPTZ` | Yes | `NULL` | | Run completion timestamp. |

---

### 3.7. `weekly_forecasts` (Predictions & Uncertainty Intervals)
Weekly point forecasts and calibrated conformal prediction intervals (80% and 90%).

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate record identifier. |
| `run_id` | `VARCHAR(64)` | No | None | **FK** (`forecast_runs.run_id` ON DELETE CASCADE) | Parent forecast run code. |
| `sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Forecasted SKU identifier. |
| `horizon_week` | `INTEGER` | No | None | | Launch age forecast horizon week (1–8). |
| `predicted_sales` | `NUMERIC(12, 2)` | No | None | | Supervised point forecast (units). Nonnegative. |
| `lower_bound_80` | `NUMERIC(12, 2)` | Yes | `NULL` | | Lower bound of 80% split conformal prediction interval. |
| `upper_bound_80` | `NUMERIC(12, 2)` | Yes | `NULL` | | Upper bound of 80% split conformal prediction interval. |
| `lower_bound_90` | `NUMERIC(12, 2)` | Yes | `NULL` | | Lower bound of 90% split conformal prediction interval. |
| `upper_bound_90` | `NUMERIC(12, 2)` | Yes | `NULL` | | Upper bound of 90% split conformal prediction interval. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Insertion timestamp. |

- **Table Constraints & Indices**:
  - `uq_forecast_run_sku_week`: `UNIQUE(run_id, sku_id, horizon_week)`
  - `ix_forecasts_run_sku`: `INDEX(run_id, sku_id)`

---

### 3.8. `analogue_matches` (Nearest Historical Precedents)
Top-K similar historical products retrieved by the analogue engine to explain cold-start launch curves.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate match identifier. |
| `run_id` | `VARCHAR(64)` | No | None | **FK** (`forecast_runs.run_id` ON DELETE CASCADE) | Associated forecast run. |
| `query_sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Cold-start SKU being forecasted. |
| `analogue_sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Comparable historical donor SKU. |
| `rank` | `INTEGER` | No | None | | Similarity ranking (1 = closest match). |
| `similarity_score`| `NUMERIC(8, 6)` | No | None | | Weighted composite similarity metric (0.0 to 1.0). |
| `observed_curve` | `JSONB` | Yes | `NULL` | | 8-week realized sales array observed for the donor SKU. |

- **Table Constraints**:
  - `uq_analogue_run_query_rank`: `UNIQUE(run_id, query_sku_id, rank)`

---

### 3.9. `inventory_recommendations` (Newsvendor Optimization)
Initial buy quantities, critical ratio calculations, expected costs, fill rates, and cold-start confidence rankings.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate recommendation identifier. |
| `run_id` | `VARCHAR(64)` | No | None | **FK** (`forecast_runs.run_id` ON DELETE CASCADE) | Associated forecast run. |
| `sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Product identifier. |
| `scenario` | `VARCHAR(32)` | No | `'BASE'` | | Cost regime (`BASE`, `CONSERVATIVE`, `AGGRESSIVE`). |
| `forecast_cumulative_8w` | `NUMERIC(12, 2)` | No | None | | 8-week cumulative point forecast sum. |
| `recommended_buy_quantity` | `INTEGER` | No | None | | Final recommended buy units (integer, MOQ & case-pack constrained). |
| `unconstrained_quantity` | `NUMERIC(12, 2)` | No | None | | Exact statistical quantile recommendation before integer packing. |
| `critical_ratio` | `NUMERIC(8, 6)` | No | None | | Newsvendor target service level $Cu / (Cu + Co)$. |
| `understock_cost_cu` | `NUMERIC(10, 2)` | No | None | | Margin loss per unit of unmet demand ($p - c$). |
| `overstock_cost_co` | `NUMERIC(10, 2)` | No | None | | Net markdown loss per excess unit ($c - s$). |
| `expected_shortage_units`| `NUMERIC(10, 2)` | No | None | | Expected unmet demand under buy quantity $Q$. |
| `expected_excess_units` | `NUMERIC(10, 2)` | No | None | | Expected unsold units under buy quantity $Q$. |
| `expected_total_cost` | `NUMERIC(12, 2)` | No | None | | Total expected mismatched inventory cost ($Cu \cdot Shortage + Co \cdot Excess$). |
| `expected_fill_rate_pct` | `NUMERIC(6, 2)` | No | None | | Expected volumetric demand fill rate (%). |
| `confidence_score` | `NUMERIC(6, 2)` | Yes | `NULL` | | Cold-Start Confidence Index (0–100). |
| `confidence_tier` | `VARCHAR(16)` | Yes | `NULL` | | Confidence tier (`HIGH`, `MEDIUM`, `LOW`). |
| `explanation_summary` | `TEXT` | Yes | `NULL` | | Human-readable non-causal attribution narrative. |
| `assumptions` | `JSONB` | Yes | `NULL` | | MOQ, case-pack, lead-time, and salvage pricing assumptions. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Recommendation creation timestamp. |

- **Table Constraints**:
  - `uq_inventory_run_sku_scenario`: `UNIQUE(run_id, sku_id, scenario)`

---

### 3.10. `cluster_allocations` (Store-Cluster Inventory Allocation)
Store-cluster inventory allocation breakdown for recommended buy quantities.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate allocation identifier. |
| `recommendation_id` | `BIGINT` | No | None | **FK** (`inventory_recommendations.id` ON DELETE CASCADE) | Parent inventory recommendation. |
| `sku_id` | `VARCHAR(64)` | No | None | **FK** (`skus.sku_id` ON DELETE CASCADE) | Product identifier. |
| `cluster_id` | `VARCHAR(64)` | No | None | **FK** (`store_clusters.cluster_id`) | Target store cluster. |
| `allocated_quantity`| `INTEGER` | No | None | | Units apportioned to this cluster. |
| `allocation_weight` | `NUMERIC(8, 4)` | No | None | | Proportional historical volume weight. |

- **Table Constraints**:
  - `uq_alloc_rec_cluster`: `UNIQUE(recommendation_id, cluster_id)`

---

### 3.11. `data_manifests` (Data Lineage & Provenance Log)
Cryptographic checksum and structural metadata tracking raw and processed datasets.

| Column | Type | Nullable | Default | Constraints & Index | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | No | Autoincrement | **PRIMARY KEY** | Surrogate manifest identifier. |
| `manifest_type` | `VARCHAR(64)` | No | None | **INDEX** (`ix_data_manifests_manifest_type`) | Artifact type (e.g., `RAW_MATURE_SKUS`, `PROCESSED_INTERVALS`). |
| `file_identifier` | `VARCHAR(255)` | No | None | | Relative file path or S3 key. |
| `sha256_checksum` | `VARCHAR(64)` | No | None | | Cryptographic SHA256 checksum of the file bytes. |
| `row_count` | `INTEGER` | No | None | | Total valid data records parsed. |
| `schema_snapshot` | `JSONB` | Yes | `NULL` | | Column types, byte sizes, and validation summary. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | | Checksum calculation timestamp. |

---

## 4. Referential Integrity, Cascades & Concurrency

### 4.1. Cascade Delete Architecture
All child analytical tables bind to `forecast_runs.run_id` with `ON DELETE CASCADE`. When an obsolete test or discarded run is deleted via `repo.delete_forecast_run(run_id)`:
1. Associated rows in `weekly_forecasts` are deleted.
2. Associated rows in `analogue_matches` are deleted.
3. Associated rows in `inventory_recommendations` are deleted.
4. Child rows in `cluster_allocations` linked to those recommendations are deleted.
5. The master catalogue `skus`, historical sales `weekly_sales`, and trained weights `model_versions` remain intact.

### 4.2. Duplicate Execution Protection
The `ForecastRepository` guarantees operational immutability. If a forecast run with `run_id` already exists with status `COMPLETED`, invoking `repo.create_forecast_run(..., prevent_duplicates=True)` immediately raises a `DuplicateRunError`. This prevents overwriting completed runs or contaminating official evaluation submissions.

---

## 5. Strict Data Isolation Policy

To prevent test-set data leakage:
1. **Physical Fencing**: `data/raw/hidden_evaluation_labels.csv` is strictly stored on disk and excluded from `init_db.py`.
2. **Schema Flagging**: All evaluation SKUs are flagged with `is_evaluation_sku = TRUE` in `skus`.
3. **Database Integrity Assertion**: In automated verification and testing, the database enforces:
   $$\text{COUNT}(WeeklySales \bowtie SKUs \text{ WHERE } is\_evaluation\_sku = \text{TRUE}) \equiv 0$$
   Any query attempting to load or join evaluation labels into model features or training views fails validation immediately.

---

## 6. Database Operations & Migration Guide

### 6.1. Running Schema Migrations (Alembic)
To upgrade the schema to the latest version:
```bash
# Using environment configuration (.env)
alembic upgrade head

# Explicit PostgreSQL target
python -m alembic -x sqlalchemy.url=postgresql+asyncpg://postgres:postgres@localhost:5432/r4_forecast_db upgrade head

# Explicit SQLite target
python -m alembic -x sqlalchemy.url=sqlite+aiosqlite:///data/r4_forecast.db upgrade head
```

To rollback a migration:
```bash
alembic downgrade -1
# Or to wipe down to clean base
alembic downgrade base
```

### 6.2. Seeding & Ingestion Script
To create all tables, ingest catalogues, historical sales, register the CatBoost cold-start model, populate the official 150-SKU evaluation run, and verify data isolation:
```bash
# SQLite (Local development default)
python scripts/init_db.py --reset --sales-limit 10000

# PostgreSQL (Production deployment)
python scripts/init_db.py --db-url "postgresql+asyncpg://postgres:postgres@localhost:5432/r4_forecast_db" --reset
```

### 6.3. Running Automated Database Tests
To run all database unit, integration, and migration lifecycle tests:
```bash
pytest tests/test_phase8_database.py -v
```
