# PHASE 7 FORECAST EXPLANATIONS & CONFIDENCE RANKING REPORT

**Audit Timestamp:** `2026-10-18T13:42:14.923235+00:00`  
**Target Population:** 150 New Cold-Start Evaluation SKUs  
**Model Version:** `v1.0.0-catboost`  
**Explainability Method:** Native TreeSHAP + Attribute Analogue Retrieval + Multi-Indicator Confidence Scoring  

---

## 1. Executive Summary: Portfolio Confidence Distribution

Across all 150 newly launched products, the **Mean Confidence Score** is **`77.5/100`** (Median: `82.9/100`).

| Confidence Tier | Score Range | SKU Count | Percentage | Recommended Commercial Posture |
| :--- | :---: | :---: | :---: | :--- |
| **HIGH** | `75.0 - 100.0` | **`110` SKUs** | `73.3%` | Automated procurement; standard case-pack buy. |
| **MEDIUM** | `60.0 - 74.9` | **`16` SKUs** | `10.7%` | Category manager sign-off; standard monitoring. |
| **LOW (Review Required)** | `< 60.0` | **`24` SKUs** | `16.0%` | **Manual merchant audit**; conservative buy / split commitment. |

> [!NOTE]
> **Calibration Notice**: As mandated by forecasting governance standards, this score is an empirical **Relative Confidence Index (0-100)** derived from observable uncertainty signals, not a Bayesian posterior probability.

---

## 2. The Ten Least-Confident SKUs (Immediate Review Roster)

These 10 products exhibit the highest forecast risk due to wide conformal intervals, distant analogue matches, large model divergence, or extreme price positioning:

| Rank | SKU ID | Product Category | Base Price | 8W Demand Forecast | 90% Prediction Interval | Confidence Score | Primary Risk Reason | Suggested Merchant Action |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **#1** | **`SKU_EVAL_120`** | Apparel | `$186.74` | `595.1` | `[465, 725]` | **`46.2`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#2** | **`SKU_EVAL_096`** | Apparel | `$194.26` | `489.2` | `[379, 599]` | **`48.8`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#3** | **`SKU_EVAL_072`** | Apparel | `$29.16` | `1322.0` | `[1066, 1578]` | **`49.0`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#4** | **`SKU_EVAL_092`** | Apparel | `$46.05` | `1213.7` | `[976, 1452]` | **`49.5`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#5** | **`SKU_EVAL_052`** | Apparel | `$43.79` | `1232.2` | `[991, 1473]` | **`50.0`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#6** | **`SKU_EVAL_116`** | Apparel | `$177.28` | `488.1` | `[378, 598]` | **`50.6`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#7** | **`SKU_EVAL_012`** | Apparel | `$96.53` | `910.1` | `[724, 1096]` | **`51.5`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#8** | **`SKU_EVAL_016`** | Apparel | `$29.13` | `902.7` | `[718, 1088]` | **`52.0`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#9** | **`SKU_EVAL_132`** | Apparel | `$65.86` | `1088.5` | `[872, 1305]` | **`52.4`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |
| **#10** | **`SKU_EVAL_136`** | Apparel | `$125.87` | `541.2` | `[422, 661]` | **`52.5`** | `DISTANT_OR_SPARSE_ANALOGUES; HIGH_MODEL_DISAGREEMENT` | Few close historical matches; conduct qualitative merchandising review of attribute positioning. |

---

## 3. Explainability Architecture & Signal Separation

To prevent confusion between statistical correlations and real-world mechanisms, explanations are separated into four distinct analytical layers:

1. **TreeSHAP Marginal Feature Contributions:** Quantifies the net directional push of each product attribute relative to the global expected training baseline ($4.55$ in log1p demand space).
2. **Historical Analogue Precedent:** Identifies the top-5 most similar mature retail products, displaying their exact observed 8-week launch trajectories.
3. **Category Launch Curve Fallback:** Documents the baseline median trajectory for the department and subcategory, including donor sample sizes ($N = 300$).
4. **Business-Rule Adjustments:** Explicitly tracks promotional marketing rules (active weeks 1–4) and non-negativity truncations.

---

## 4. Deep-Dive Sample Audit Record
Exemplar audit report for benchmark SKU (`SKU_EVAL_001`):

- **Product Name:** ValueCraft New Sneakers Grey
- **Category / Subcategory:** `Footwear / Sneakers`
- **Retail MSRP:** `$104.60`
- **Cumulative 8-Week Forecast:** **`501.4` units**
- **Calibrated 90% Conformal Interval:** `[389.2, 613.6]` units
- **Cold-Start Confidence Score:** **`84.0/100`** (HIGH)

### Top Empirical TreeSHAP Drivers:
| Feature Name | Net 8-Week SHAP Contribution | Directional Impact | Non-Causal Interpretation |
| :--- | :---: | :---: | :--- |
| `launch_week_age` | **`+0.1091`** | Upward | Statistically associated with higher launch velocity in mature cohort. |
| `cos_launch_month` | **`+0.0380`** | Upward | Statistically associated with higher launch velocity in mature cohort. |
| `is_holiday_week` | **`+0.0086`** | Upward | Statistically associated with higher launch velocity in mature cohort. |
| `brand_tier` | **`-1.4662`** | Downward | Statistically associated with lower introductory demand in mature cohort. |
| `marketing_flag` | **`-0.7396`** | Downward | Statistically associated with lower introductory demand in mature cohort. |
| `brand` | **`-0.4550`** | Downward | Statistically associated with lower introductory demand in mature cohort. |

### Closest Historical Analogue Matches:
| Analogue SKU | Similarity | Category | Subcategory | Base Price | Observed 8W Sales |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `SKU_HIST_0417` | **`0.898`** | Footwear | Sneakers | `$159.72` | `452` units |
| `SKU_HIST_0057` | **`0.895`** | Footwear | Sneakers | `$108.42` | `510` units |
| `SKU_HIST_0237` | **`0.894`** | Footwear | Sneakers | `$100.57` | `490` units |

### Generated Commercial Narrative:
> *"SKU 'SKU_EVAL_001' (ValueCraft New Sneakers Grey) in 'Footwear / Sneakers' is forecasted to achieve 501.4 units over its initial 8-week launch period (90% prediction interval: [389.2, 613.6] units). The Cold-Start Confidence Index is 84.0/100 (HIGH confidence). Primary positive empirical drivers include 'launch_week_age' (+0.11), 'cos_launch_month' (+0.04). Primary downward empirical drivers include 'brand_tier' (-1.47), 'marketing_flag' (-0.74). The closest historical analogue is SKU_HIST_0417 (similarity: 0.898, observed 8-week sales: 452 units). Note: TreeSHAP contributions represent statistical associations learned from historical mature launches and do not imply direct business causality."*

---

## 5. Confidence Score Component Weights & Formula

$$\text{Confidence Score} = 100 \times \sum_{k=1}^5 w_k \cdot S_k$$

| Indicator Component ($S_k$) | Weight ($w_k$) | Measurement Mechanism | Low Score Condition |
| :--- | :---: | :--- | :--- |
| **Prediction Interval Spread** | `30%` | Relative width: $(U_{90} - L_{90}) / \hat{D}$ | Wide conformal interval ($	ext{Width} > 65\%$ of demand). |
| **Analogue Quality** | `25%` | Mean similarity of top-5 historical matches | Poor matches (similarity $< 0.82$). |
| **Model Consensus** | `20%` | Divergence between GBDT and Analogue curves | Disagreement $> 25\%$ between independent models. |
| **Category Track Record** | `15%` | Historical held-out test WAPE for category | Volatile department (historical test $	ext{WAPE} > 0.265$). |
| **Attribute Typicality** | `10%` | Price Z-score relative to category peers | Severe pricing outlier ($|z| > 2.2$) or rare attributes. |