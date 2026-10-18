# PHASE 4 BENCHMARK REPORT — SUPERVISED DEMAND FORECASTING

**Benchmark Date:** `2026-10-18T13:20:58.320359+00:00`  
**Target Population:** 200 Held-Out Historical Cold-Start Launch SKUs (Strict SKU Fencing)  
**Evaluation Metric:** Weighted Absolute Percentage Error (WAPE)  

## 1. Executive Summary & Model Selection
Across all evaluated candidate models, the **Supervised CatBoost GBDT Regressor** configured with **`MAE`** (L1 Loss) achieved the lowest test WAPE and lowest cumulative forecast error.

### Benchmark Comparison Table (Test Split: 200 Held-Out SKUs)

| Model Architecture | Weekly WAPE | Weekly RMSE | Weekly MAE | Cumul. 8W WAPE | Cumul. 8W RMSE | Bias % | Category Stability (Std) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Global Empirical Median** | **`0.3469`** | `52.19` | `36.80` | **`0.2590`** | `309.92` | `-10.45%` | `0.0071` |
| **Category/Subcategory Baseline** | **`0.3410`** | `51.38` | `36.18` | **`0.2488`** | `298.59` | `-9.53%` | `0.0124` |
| **Top-5 Analogue Retrieval** | **`0.2855`** | `40.58` | `30.29` | **`0.1279`** | `155.50` | `-3.10%` | `0.0102` |
| **Supervised CatBoost GBDT** | **`0.2561`** | `35.73` | `27.17` | **`0.1038`** | `118.81` | `-3.26%` | `0.0080` |

## 2. Multi-Horizon WAPE Breakdown ($W_1$ through $W_8$)

| Model | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Global Empirical Median | `0.350` | `0.344` | `0.337` | `0.385` | `0.334` | `0.338` | `0.354` | `0.317` |
| Category/Subcategory Baseline | `0.353` | `0.336` | `0.330` | `0.382` | `0.320` | `0.323` | `0.352` | `0.310` |
| Top-5 Analogue Retrieval | `0.276` | `0.279` | `0.311` | `0.293` | `0.273` | `0.277` | `0.303` | `0.270` |
| Supervised CatBoost GBDT | `0.252` | `0.250` | `0.281` | `0.250` | `0.259` | `0.242` | `0.261` | `0.252` |

## 3. Merchandise Category Breakdown (WAPE by Category)

| Model | Apparel | Footwear | Accessories | Home | Category Std |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Global Empirical Median | `0.350` | `0.336` | `0.346` | `0.356` | `0.0071` |
| Category/Subcategory Baseline | `0.324` | `0.339` | `0.346` | `0.358` | `0.0124` |
| Top-5 Analogue Retrieval | `0.277` | `0.278` | `0.287` | `0.302` | `0.0102` |
| Supervised CatBoost GBDT | `0.254` | `0.246` | `0.267` | `0.260` | `0.0080` |

## 4. Hyperparameter & Architecture Configuration
- **Selected Objective:** `MAE` (directly optimizes L1 loss / WAPE numerator)
- **Target Transform:** `log1p`
- **Tuned Hyperparameters:** `{'depth': 6, 'learning_rate': 0.03, 'l2_leaf_reg': 3.0}`
- **Inference Interface:** `ColdStartPredictor` exposed in `src/models/supervised.py`

## 5. Why the Supervised Model Is Preferred & Failure Modes
### Why Preferred:
1. **Continuous Attribute Sensitivity**: Unlike category baselines, CatBoost non-linearly conditions on exact MSRP/price elasticity and brand tier.
2. **Cross-Sectional Sharing**: Learns shared launch decay rates across the entire catalog while preserving category-specific level shifts.
3. **Objective Alignment**: Training directly with MAE (L1 loss) minimizes absolute error, perfectly matching the competition's WAPE metric.
4. **Native Handling of High-Cardinality Categoricals**: CatBoost applies target statistics across random permutations, preventing target leakage without arbitrary one-hot or ordinal encodings.

### Conditions Under Which the Model May Fail:
1. **Extreme Price Outliers**: Products priced significantly outside the historical training support ($p < \$10$ or $p > \$300$) may suffer tree-clipping.
2. **Radically Novel Categories**: Completely unseen departments fallback to global tree leaf averages without specific historical priors.
3. **Exogenous Supply Shocks / Stockouts**: The model forecasts unconstrained demand; physical inventory bottlenecks will cause positive forecast bias in store operations.