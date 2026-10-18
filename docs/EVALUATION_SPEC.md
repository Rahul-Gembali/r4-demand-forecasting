# EVALUATION SPECIFICATION — R4 New Product Demand Forecasting

**Specification Version:** 1.0.0  
**Target Evaluation Cohort:** 150 New Cold-Start SKUs  
**Forecasting Horizon:** 8 Weeks ($W_1$ through $W_8$)  
**Status:** Reference Implementation (Official `evaluate.py` blocked per BLK-002)

---

## 1. Evaluation Overview & Objective

The objective of the R4 New Product Demand Forecasting competition/system is to evaluate the commercial accuracy of cold-start demand forecasts generated for **150 newly launched SKUs** over their initial eight-week lifecycle ($W_1, W_2, \dots, W_8$).

Because new products incur heavy inventory penalties (excess holding cost vs. lost sales and brand churn), the evaluation metrics must measure both **absolute scale deviation** and **aggregate bias**.

---

## 2. Mathematical Metric Definitions

Let $N = 150$ be the number of evaluation SKUs, $H = 8$ be the forecast horizon weeks, and $S$ be the set of store clusters (if evaluated at store-cluster level, or aggregated at enterprise level).

Let:
- $y_{i, h}$: Actual realized weekly sales for SKU $i$ at horizon week $h \in \{1, \dots, 8\}$.
- $\hat{y}_{i, h}$: Predicted weekly sales for SKU $i$ at horizon week $h \in \{1, \dots, 8\}$.
- $e_{i, h} = \hat{y}_{i, h} - y_{i, h}$: Forecast error.

---

### 2.1 Primary Metric: Weighted Absolute Percentage Error (WAPE)
WAPE (also known as MAD/Mean ratio) avoids the division-by-zero pathology of classical MAPE when actual sales are zero.

$$\text{WAPE} = \frac{\sum_{i=1}^{N} \sum_{h=1}^{H} |y_{i, h} - \hat{y}_{i, h}|}{\sum_{i=1}^{N} \sum_{h=1}^{H} y_{i, h}}$$

- **Per-Week WAPE ($W_h$)**:
  $$\text{WAPE}_h = \frac{\sum_{i=1}^{N} |y_{i, h} - \hat{y}_{i, h}|}{\sum_{i=1}^{N} y_{i, h}}$$
- **Optimization target**: Models optimizing L1 loss (MAE) directly minimize WAPE.

---

### 2.2 Secondary Metric: Root Mean Squared Error (RMSE)
Measures sensitivity to large outlier forecast blunders (which lead to catastrophic warehouse shortages or overstock).

$$\text{RMSE} = \sqrt{\frac{1}{N \cdot H} \sum_{i=1}^{N} \sum_{h=1}^{H} (y_{i, h} - \hat{y}_{i, h})^2}$$

---

### 2.3 Secondary Metric: Mean Absolute Error (MAE)
$$\text{MAE} = \frac{1}{N \cdot H} \sum_{i=1}^{N} \sum_{h=1}^{H} |y_{i, h} - \hat{y}_{i, h}|$$

---

### 2.4 Bias & Tracking Signal
Measures systematic over-forecasting (carrying cost penalty) or under-forecasting (stockout penalty).

$$\text{Forecast Bias (\%)} = \frac{\sum_{i=1}^{N} \sum_{h=1}^{H} (\hat{y}_{i, h} - y_{i, h})}{\sum_{i=1}^{N} \sum_{h=1}^{H} y_{i, h}} \times 100\%$$

- A positive bias indicates systemic over-forecasting.
- A negative bias indicates systemic under-forecasting.

---

### 2.5 Probabilistic / Quantile Loss (Pinball Loss)
For inventory safety-stock planning (e.g., P50 median and P90 replenishment buffers), the pinball loss at quantile $\tau \in (0, 1)$ is:

$$L_{\tau}(y, \hat{y}) = \max(\tau (y - \hat{y}), (1 - \tau)(\hat{y} - y))$$

$$\text{Pinball Loss}_{\tau} = \frac{1}{N \cdot H} \sum_{i=1}^{N} \sum_{h=1}^{H} L_{\tau}(y_{i, h}, \hat{y}^{(\tau)}_{i, h})$$

---

## 3. Submission & Interface Specification

### 3.1 Input Prediction File Format
The evaluation engine expects predictions formatted as a CSV or Parquet file adhering to the following schema:

| Column Name | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `sku_id` | `VARCHAR(64)` | Unique SKU identifier | Must match exactly the 150 evaluation SKUs |
| `horizon_week` | `INTEGER` | Lifecycle week index | Exactly values $1, 2, 3, 4, 5, 6, 7, 8$ |
| `predicted_sales` | `FLOAT` | Predicted weekly unit volume | $\ge 0.0$, finite (no NaN, null, or Inf) |

Total required rows in submission:
$$\text{Row Count} = 150 \text{ SKUs} \times 8 \text{ Weeks} = 1,200 \text{ rows}$$

*(Note: If evaluation is evaluated at store-cluster level, $\text{Rows} = 150 \times 8 \times K \text{ clusters}$. The interface adapter supports both enterprise and cluster-level evaluations).*

### 3.2 Ground-Truth Evaluation Format
The hidden ground truth file must contain matching keys:
```csv
sku_id,horizon_week,actual_sales
SKU_EVAL_001,1,142.0
SKU_EVAL_001,2,118.0
...
```

---

## 4. Operational & Information Security Constraints

1. **Strict No-Leakage Isolation**: Under no circumstance should actual evaluation labels be incorporated into feature stores, training sets, or cross-validation routines.
2. **Deterministic Reproducibility**: Evaluation score generation must be bitwise reproducible given fixed predictions and ground truth.
3. **Format Validation**: Submissions containing missing SKU weeks, negative forecasts, or NaN/Inf values fail validation immediately with a descriptive schema error.
