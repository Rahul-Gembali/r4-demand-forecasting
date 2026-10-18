# DATA AUDIT REPORT — R4 Project Discovery & Initial Inspection

**Document Version:** 1.0.0  
**Phase:** Phase 1 — Project Initialization and Data Discovery  
**Audit Timestamp:** 2026-10-18  
**Lead Auditor:** Senior Data Engineer & Machine Learning Architect  

---

## 1. Executive Summary & Audit Scope

The primary objective of Phase 1 is to discover, inventory, and validate all physical source datasets, schema definitions, and official evaluator implementations for the **R4 New Product Demand Forecasting** project. 

The analytical problem requires forecasting weekly sales for the first eight weeks ($W_1$ to $W_8$) of **150 new cold-start SKUs** using historical sales and attribute distributions learned from approximately **1,200 mature or discontinued reference SKUs**, across store clusters and holiday calendar variations.

In strict compliance with the project constraints:
- **No data fabrication**: Zero synthetic values, made-up statistics, or assumed distributions have been manufactured.
- **Zero label leakage**: No hidden ground-truth labels for the 150 evaluation SKUs are exposed.
- **Source data immutability**: Raw data sources are treated as strictly read-only.
- **No unverified assumptions**: Column names, data types, and file formats are verified via filesystem inspection scripts rather than presumed.

---

## 2. Exhaustive Filesystem Discovery Log

An exhaustive search was conducted across all mounted file system volumes (`C:\`, `D:\`, `E:\`, `F:\`) using PowerShell and automated Python search routines:

| Mount Point | Volume Name | Total Capacity | Free Space | Search Scope & Criteria | Files Identified |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `E:\` | Volume (E:) | ~302 GB | ~302 GB | Targeted directory scan for R4, forecast, demand, evaluate.py | `CampusQuiz`, `personal-ai-workspace`, `prototype`, `prototype.py` (Unrelated) |
| `C:\` | OS (C:) | ~223 GB | ~121 GB | User downloads, desktop, documents, recent shortcuts, scratch | PPTX submission templates; zero R4 tabular data files |
| `D:\` | Data (D:) | ~327 GB | ~0.01 GB | Full drive inspection | Zero R4 demand forecasting assets |
| `F:\` | Volume (F:) | ~301 GB | ~300 GB | Drive file listing | Unrelated learning projects and archives |

### 2.1 File Discovery Matrix

| Expected Asset Category | Target File Pattern | Status on Disk | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Historical Weekly Sales** | `*sales*.csv`, `*sales*.parquet`, `*sales*.xlsx` | **NOT FOUND** | Source data pending ingestion into `data/raw/` |
| **Product Attributes** | `*sku*.csv`, `*product*.csv`, `*catalog*` | **NOT FOUND** | Source data pending ingestion into `data/raw/` |
| **Store Clusters** | `*store*.csv`, `*cluster*.csv` | **NOT FOUND** | Source data pending ingestion into `data/raw/` |
| **Holiday Calendar** | `*holiday*.csv`, `*calendar*.csv` | **NOT FOUND** | Source data pending ingestion into `data/raw/` |
| **Evaluation SKU Cohort** | `*eval*.csv`, `*test*.csv`, `*150*` | **NOT FOUND** | List of 150 target new SKUs pending ingestion |
| **Official Evaluator** | `evaluate.py`, `evaluator.py`, `metric*.py` | **NOT FOUND** | Official evaluation script pending ingestion |

---

## 3. Data Integrity & Schema Audit Findings

Because the raw input files are currently absent from the physical file system, formal data metrics (row counts, null percentages, distinct SKU counts, timestamp bounds) cannot be observed directly without violating the non-fabrication constraint.

The audit has established the following findings and automated verification protocols:

### 3.1 Date Ranges & Launch Representation
- **Target Horizon**: 8 weeks post-launch ($W_1$ through $W_8$).
- **Launch Determination**: When raw sales transactions become available, the launch date for each reference SKU must be computed dynamically as either:
  1. The explicit `launch_date` attribute if present in product master records.
  2. The first non-zero sales week recorded in the historical transaction panel:
     $$T_i^{launch} = \min \{ t \mid \text{units\_sold}_{i, t} > 0 \}$$
- **Verification Rule**: Any transaction occurring prior to $T_i^{launch}$ must be flagged as pre-launch inventory movement or invalid noise.

### 3.2 Distinguishability of Missing Sales, Zero Sales, and Stockouts
The data inspection engine (`scripts/inspect_data.py`) incorporates automated classification logic to test whether source data separates:
- **True Zero Sales**: Grid entry exists with `units_sold = 0` and full shelf availability (`days_in_stock = 7` or stockout indicator = `False`).
- **Censored Stockouts**: Grid entry with `units_sold >= 0` where `days_in_stock < 7` or `is_stockout = True`.
- **Structural Gaps (Missing Rows)**: Absent $(sku, store, week)$ tuple indicating non-distribution or unrecorded weeks.

---

## 4. Formal Project Blockers (Phase 1)

| Blocker ID | Severity | Description | Required Action |
| :--- | :--- | :--- | :--- |
| **BLK-001** | **BLOCKING** | **Raw Dataset Files Not Ingested**<br>Neither the ~1,200 mature reference SKU history nor the 150 cold-start SKU attribute tables exist on disk. | User or automated ingest pipeline must copy the raw CSV, Parquet, or XLSX files into `E:\r4-demand-forecasting\data\raw/`. |
| **BLK-002** | **BLOCKING** | **Official `evaluate.py` Not Available**<br>The benchmark evaluation script has not been provided in the repository. | Ingest the official `evaluate.py` or authorize the reference WAPE/RMSE implementation defined in `docs/EVALUATION_SPEC.md`. |

---

## 5. Automated Data Inspection Protocol

To immediately audit the raw dataset as soon as it is placed in `data/raw/`, a reproducible CLI tool has been provided:

```powershell
# Run the discovery and schema validation inspection
python scripts/inspect_data.py --data-dir E:\r4-demand-forecasting\data\raw --output docs/data_audit_results.json
```

The script automatically executes:
1. Recursive file enumeration (`.csv`, `.parquet`, `.xlsx`, `.json`).
2. Schema extraction (column names, inferred dtypes, memory footprint).
3. Null value and infinite value accounting per column.
4. Duplicate row detection and primary key uniqueness testing.
5. Automated heuristic detection of SKU identifiers, timestamps, target sales, store clusters, and holiday attributes.
6. Generation of machine-readable `data_audit_results.json` and human-readable audit logs.
