# FEATURE SCHEMA SPECIFICATION — R4 New Product Demand Forecasting

**Schema Version:** 2.0.0  
**Phase:** Phase 2 — Data Pipeline and Data Quality  
**Storage Formats:** Parquet (`data/processed/train_features.parquet`, `data/processed/inference_features.parquet`)  

---

## 1. Feature Architecture Overview

Cold-start forecasting evaluates demand across introductory lifecycle weeks ($W_1$ through $W_8$) for 150 target products with zero historical sales. To ensure maximum generalization and zero data leakage:
1. All feature representations are computed from cross-sectional attributes, historical launch alignments, store cluster mappings, and exogenous calendar dynamics.
2. Feature transformations (vocabularies, price imputations, categorical mappings) are fitted strictly on the ~1,200 mature reference SKUs.
3. Unseen categories in the 150 target SKUs are mapped deterministically to `_UNKNOWN_`.
4. Target sales values (`units_sold`) are completely nullified (`None`) in the inference feature set to guarantee zero label exposure.

---

## 2. Feature Dictionary

| Feature Name | Logical Type | In-Memory Dtype | Cardinality / Range | Description & Calculation Logic |
| :--- | :--- | :--- | :--- | :--- |
| `sku_id` | Alphanumeric | `object` / `string` | 1,350 unique SKUs | Unique product identifier. |
| `store_id` | Alphanumeric | `object` / `string` | Stores / Enterprise | Store location identifier (or `ENTERPRISE_AGG` for national rollouts). |
| `cluster_id` | Categorical | `object` / `string` | e.g., 3-5 clusters | Store demographic / velocity cluster assignment. |
| `launch_week_age` | Discrete Ordinal | `int64` | `1, 2, 3, 4, 5, 6, 7, 8` | Weeks elapsed since commercial introduction: $\lfloor(t - T_i^{launch}) / 7\rfloor + 1$. |
| `category` | Categorical | `object` / `string` | ~4-8 categories | Primary department (Apparel, Footwear, Accessories, Home). |
| `subcategory` | Categorical | `object` / `string` | ~15-30 subcategories | Granular classification (e.g., Jackets, Sneakers). |
| `colour` | Categorical | `object` / `string` | ~8-15 shades | Dominant product shade (Black, Navy, Camel, etc.). |
| `material` | Categorical | `object` / `string` | ~8-12 materials | Primary composition (Cotton, Wool, Leather, etc.). |
| `base_price` | Continuous | `float64` | $\ge 0.01$ | Regular retail shelf price at introduction. |
| `log_base_price` | Continuous | `float64` | $\ge 0.0$ | $\ln(1 + \text{base\_price})$ stabilizing price skew. |
| `price_band` | Categorical Enum | `object` / `string` | 4 bands | Derived: `Budget` (<$25), `Mid-Range` ($25-$75), `Premium` ($75-$150), `Luxury` ($\ge$150). |
| `brand` | Categorical | `object` / `string` | ~5-20 brands | Commercial brand identifier. |
| `brand_tier` | Categorical Enum | `object` / `string` | 3 tiers | Positioning: `Tier 1 National`, `Tier 2 Regional`, `Tier 3 Value`. |
| `launch_month` | Discrete Cyclic | `int64` | `1` to `12` | Calendar month of introductory launch. |
| `sin_launch_month` | Continuous | `float64` | $[-1.0, 1.0]$ | $\sin(2\pi \cdot \text{launch\_month} / 12)$. |
| `cos_launch_month` | Continuous | `float64` | $[-1.0, 1.0]$ | $\cos(2\pi \cdot \text{launch\_month} / 12)$. |
| `marketing_flag` | Binary Flag | `int64` | `0` or `1` | Commercial launch burst rule: `1` during introductory $W_1..W_4$ if marketing supported, `0` otherwise. |
| `is_holiday_week` | Binary Flag | `int64` | `0` or `1` | `1` if horizon week contains a major promotional or cultural event. |
| `holiday_name` | Categorical | `object` / `string` | Named events | Specific designation (e.g., Black Friday, Christmas, Diwali, None). |
| `week_of_year` | Discrete Cyclic | `int64` | `1` to `52` | ISO calendar week of the horizon date. |
| `sin_week_of_year` | Continuous | `float64` | $[-1.0, 1.0]$ | $\sin(2\pi \cdot \text{week\_of\_year} / 52)$. |
| `cos_week_of_year` | Continuous | `float64` | $[-1.0, 1.0]$ | $\cos(2\pi \cdot \text{week\_of\_year} / 52)$. |
| `observation_status`| Status Enum | `object` / `string` | 3 statuses | `OBSERVED_POSITIVE`, `GENUINE_ZERO`, or `MISSING_OBSERVATION`. |
| `is_target_eval_sku`| Boolean | `bool` | `True` / `False` | Fencing flag: `True` for the 150 test SKUs, `False` for training SKUs. |
| `units_sold` | Continuous Target| `float64` / `None` | $\ge 0.0$ | Gross weekly units sold. **Strictly `None` in inference feature set**. |

---

## 3. Data Integrity & Leakage Prevention Rules

1. **Target Feature Isolation**: `units_sold` is strictly omitted from the inference matrix.
2. **Deterministic Category Fencing**: The encoder registers unique categorical tokens during the training fit. Any novel token in inference features is mapped to `_UNKNOWN_` rather than failing or creating out-of-vocabulary artifacts.
3. **Imputation Fencing**: Missing prices are imputed using the training set median ($\$49.99$) without using test SKU distributions.
4. **Stockout Non-Invention**: Because explicit stockout logs (`days_in_stock` / `stockout_flag`) were not captured in raw transactional point-of-sale logs, the pipeline treats observed zero sales as `GENUINE_ZERO` and unobserved weeks as `MISSING_OBSERVATION`, without fabricating pseudo-censoring adjustments.
