# DATA QUALITY & INTEGRITY AUDIT REPORT

**Audit Timestamp:** `2026-10-18T12:59:32.542561+00:00`  
**Overall Compliance Status:** **`PASSED`**  
**Strict Target Leakage Isolation:** **`PASSED (ZERO LEAKAGE)`**  

## 1. Dataset Dimensions
- **Training Dataset Rows:** `43,173` across `1200` mature SKUs
- **Inference Dataset Rows:** `1,200` across `150` cold-start SKUs

## 2. Quality Check Results

| Check Name | Status | Observed Value | Threshold | Details |
| :--- | :--- | :--- | :--- | :--- |
| `target_sku_count_alignment` | ✅ PASSED | `150` | `150` | Inference set contains 150 target SKUs (Expected 150) |
| `target_evaluation_isolation_leakage` | ✅ PASSED | `0` | `0` | 0 evaluation SKUs found in training set (Strict zero overlap required) |
| `hidden_evaluation_labels_protection` | ✅ PASSED | `0` | `0` | Inference features target exposure: 0 values present (MUST BE NULL) |
| `launch_week_age_alignment` | ✅ PASSED | `[1, 2, 3, 4, 5, 6, 7, 8]` | `[1, 2, 3, 4, 5, 6, 7, 8]` | Launch week age range: [1, 2, 3, 4, 5, 6, 7, 8] (Expected [1, 2, 3, 4, 5, 6, 7, 8]) |
| `marketing_flag_business_rule_validation` | ✅ PASSED | `0.666` | `0.0` | Marketing intensity: Weeks 1-4 avg=0.67, Weeks 5-8 avg=0.00 |

## 3. Stockout Censoring & Genuine Zero Sales Policy
> Stockout information (days_in_stock / stockout_flag) was audited. Where not present in source transactional feeds, the pipeline explicitly preserves unobserved status and DOES NOT fabricate synthetic stockout censors.

## 4. Marketing Flag Business Rule Adherence
> In accordance with commercial launch policy, promotional marketing support is concentrated during the initial introductory burst (Weeks 1 through 4).