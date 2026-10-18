# Data Directory Conventions

This directory holds all data partitions for the R4 New Product Demand Forecasting system.

## Directory Layout
- `raw/`: Immutable source data (e.g. CSV, Parquet, XLSX) as received from the competition/enterprise source.
  - Expected entities:
    - Weekly sales transactions (`historical_sales`)
    - Product master & metadata (`sku_attributes` or `product_catalog`)
    - Store hierarchy & cluster mappings (`store_clusters`)
    - Calendar & holiday schedule (`holiday_calendar`)
    - Evaluation SKU roster (150 new SKUs without sales history)
  - **Rule**: Never edit, overwrite, or mutate files in `raw/`.
- `interim/`: Intermediate representations, harmonized column names, validated dates, and unified join views.
- `processed/`: Cold-start feature stores, historical launch profiles, similarity matrices, and cross-validation splits.

## Blocker Notice (Phase 1)
As of Phase 1 initialization, raw dataset files have not yet been placed into `data/raw/`. Once provided, execute:
```bash
python scripts/inspect_data.py --data-dir data/raw
```
to automatically discover schemas, validate column mappings, and compile the audit ledger.
