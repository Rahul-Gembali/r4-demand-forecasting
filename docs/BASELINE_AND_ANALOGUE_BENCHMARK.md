# PHASE 3 BENCHMARK REPORT — BASELINES & ANALOGUE RETRIEVAL

**Evaluation Date:** `2026-10-18T13:06:44.995371+00:00`  
**Validation Cohort:** `200` held-out SKUs (1000 train / 200 held-out (~16.7%))  
**Evaluation Target:** Enterprise sales across Launch Weeks $W_1$ through $W_8$  

## 1. Model Comparison Summary (Offline Held-Out Launches)

| Model Architecture | WAPE (Primary) | RMSE | MAE | Bias % | Evaluated SKUs | Total Eval Points |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Global Empirical Median** | **`0.3461`** | `50.60` | `35.94` | `-7.43%` | `200` | `1,600` |
| **Category/Subcategory Baseline (Median)** | **`0.3445`** | `50.29` | `35.77` | `-5.94%` | `200` | `1,600` |
| **Category/Subcategory Baseline (Mean)** | **`0.3528`** | `50.04` | `36.63` | `+1.08%` | `200` | `1,600` |
| **Top-5 Analogue Retrieval (Power-2 Weighted)** | **`0.2942`** | `41.04` | `30.55` | `-2.16%` | `200` | `1,600` |

## 2. Multi-Horizon WAPE Breakdown ($W_1$ to $W_8$)

| Model | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Global Empirical Median | `0.365` | `0.355` | `0.352` | `0.357` | `0.316` | `0.327` | `0.337` | `0.329` |
| Category/Subcategory Baseline (Median) | `0.366` | `0.357` | `0.346` | `0.360` | `0.314` | `0.325` | `0.334` | `0.319` |
| Category/Subcategory Baseline (Mean) | `0.369` | `0.374` | `0.355` | `0.371` | `0.320` | `0.327` | `0.339` | `0.328` |
| Top-5 Analogue Retrieval (Power-2 Weighted) | `0.295` | `0.304` | `0.280` | `0.305` | `0.293` | `0.299` | `0.274` | `0.303` |

## 3. Methodological Observations & Limitations
- Category baselines predict static profiles that ignore granular product attributes (price, material, colour).
- Analogue retrieval provides adaptive attribute-specific forecasts, but variance is sensitive to the donor pool density.
- Both models lack cross-sectional gradient boosting or complex interactions, which will be addressed in Phase 4.
- Evaluation was conducted on enterprise-aggregated weekly totals; store-level allocation requires spatial disaggregation.
