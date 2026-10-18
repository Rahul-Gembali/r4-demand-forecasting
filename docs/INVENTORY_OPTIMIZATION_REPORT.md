# PHASE 6 INVENTORY & BUY QUANTITY OPTIMIZATION REPORT

**Optimization Date:** `2026-10-18T13:35:01.018411+00:00`  
**Target Population:** 150 New Cold-Start Evaluation SKUs  
**Planning Horizon:** 8 Weeks (Introductory Lifecycle Period)  
**Optimization Framework:** Single-Period Stochastic Newsvendor Model  

---

## 1. Executive Summary & Enterprise Portfolio Sizing

| Planning Dimension | Conservative Scenario | Base Scenario (Standard) | Aggressive Scenario |
| :--- | :---: | :---: | :---: |
| **Strategic Posture** | Margin-Preserving / Risk-Averse | Balanced Retail Standard | High-Availability / Growth |
| **Total Portfolio Buy Quantity** | **`107,904` units** | **`117,162` units** | **`123,216` units** |
| **Portfolio Safety Stock** | `-4,565 units` | `+4,693 units` | `+10,747 units` |
| **Expected Enterprise Fill Rate** | `91.2%` | **`96.7%`** | `98.1%` |
| **Expected Total Newsvendor Cost** | - | **`$474,664.20`** | - |

---

## 2. Mathematical Formulation & Economic Objective

For each introductory SKU $i$, the initial buy quantity $Q_i$ minimizes the expected financial mismatch cost:

$$\min_{Q_i} \mathbb{E}[\text{Cost}(Q_i)] = C_u \cdot \mathbb{E}[\max(D_i - Q_i, 0)] + C_o \cdot \mathbb{E}[\max(Q_i - D_i, 0)]$$

where:
- $D_i$: Total cumulative customer demand over the initial 8-week horizon.
- $C_u$: Understock cost per unit (lost gross margin + lost customer goodwill).
- $C_o$: Overstock cost per unit (unit purchase cost - salvage recovery value + holding costs).
- $\text{Critical Ratio (CR)} = \frac{C_u}{C_u + C_o}$.
- The unconstrained continuous optimal quantity satisfies $F_D(Q_i^*) = \text{CR} \iff Q_i^* = F_D^{-1}(\text{CR})$.

> [!IMPORTANT]
> **Cumulative Horizon Distinction**: Initial buy quantities are strictly optimized against the **cumulative 8-week demand distribution**, not by summing weekly marginal quantiles. As established in Phase 5, summing weekly quantiles creates an over-inflated, invalid coverage buffer.

---

## 3. Scenario Derivation & Cost Parameterization

Because supplier cost price and salvage rates are not natively recorded in raw retail POS feeds, we define three transparent, auditable business scenarios:

| Cost Scenario | Gross Margin % | Salvage % of Cost | Goodwill Penalty % of Price | Typical Critical Ratio | Strategic Intent |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Conservative** | `35%` | `20%` | `0%` | **`0.37`** | Protects capital; avoids heavy markdown liquidations. |
| **Base (Benchmark)** | `50%` | `40%` | `5%` | **`0.61`** | Standard balanced retail posture. |
| **Aggressive** | `60%` | `50%` | `15%` | **`0.77`** | Prevents lost sales and churn during product launches. |

---

## 4. Sensitivity Analysis across Critical Ratio Spectrum
Sensitivity sweep for benchmark launch SKU (`SKU_EVAL_001`, Expected 8-Week Demand = `501`):

| Critical Ratio (CR) | Buy Quantity ($Q$) | Safety Stock ($\\Delta$) | Expected Shortage | Expected Excess | Expected Fill Rate | Expected Total Cost |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`0.25`** | **`455`** | `-46` | `56.5` units | `10.1` units | `88.7%` | `$1,058.02` |
| **`0.35`** | **`475`** | `-26` | `42.4` units | `16.0` units | `91.5%` | `$1,422.93` |
| **`0.50`** | **`501`** | `+0` | `27.4` units | `27.0` units | `94.5%` | `$1,992.39` |
| **`0.60`** | **`519`** | `+17` | `19.3` units | `36.9` units | `96.2%` | `$2,411.82` |
| **`0.70`** | **`537`** | `+35` | `13.0` units | `48.6` units | `97.4%` | `$2,894.03` |
| **`0.80`** | **`559`** | `+57` | `7.6` units | `65.2` units | `98.5%` | `$3,495.41` |
| **`0.85`** | **`572`** | `+70` | `5.3` units | `75.9` units | `98.9%` | `$3,881.39` |

---

## 5. Operational Constraints Integration
The inventory engine integrates operational vendor constraints:
1. **Non-Negative Integer Quantities:** All purchase orders are discrete integers $Q \in \mathbb{Z}_{\ge 0}$.
2. **Case-Pack Multiple ($CP = 6$):** Orders are rounded to master carton multiples by evaluating the exact expected total cost function $\mathbb{E}[\text{Cost}(Q)]$ between floor and ceiling packs.
3. **Minimum Order Quantity (MOQ = 24):** If $Q^* < \text{MOQ}$, the system compares $\mathbb{E}[\text{Cost}(\text{MOQ})]$ against $\mathbb{E}[\text{Cost}(0)] = C_u \cdot \mu$ to decide whether to place the minimum order or cancel the launch.

---

## 6. Sample Buy Recommendations (Top 10 SKUs)

| SKU ID | Category | Base Price | 8W Demand Forecast | 90% Conformal Interval | Base Buy Qty | Base Fill Rate | Conservative Qty | Aggressive Qty |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`SKU_EVAL_001`** | Footwear | `$104.60` | `501.4` | [389.2, 613.6] | **`522`** | `96.4%` | `480` | `552` |
| **`SKU_EVAL_002`** | Accessories | `$165.34` | `721.3` | [568.5, 874.1] | **`750`** | `96.6%` | `690` | `792` |
| **`SKU_EVAL_003`** | Home | `$141.81` | `559.2` | [436.1, 682.3] | **`582`** | `96.5%` | `534` | `618` |
| **`SKU_EVAL_004`** | Apparel | `$176.78` | `705.8` | [555.8, 855.9] | **`738`** | `96.8%` | `678` | `774` |
| **`SKU_EVAL_005`** | Footwear | `$114.64` | `588.2` | [459.7, 716.7] | **`612`** | `96.5%` | `564` | `648` |
| **`SKU_EVAL_006`** | Accessories | `$177.95` | `488.0` | [378.3, 597.6] | **`510`** | `96.5%` | `468` | `540` |
| **`SKU_EVAL_007`** | Home | `$183.59` | `618.5` | [484.4, 752.6] | **`648`** | `96.8%` | `594` | `678` |
| **`SKU_EVAL_008`** | Apparel | `$136.81` | `661.0` | [519.1, 802.9] | **`690`** | `96.7%` | `636` | `726` |
| **`SKU_EVAL_009`** | Footwear | `$85.13` | `824.1` | [653.0, 995.3] | **`858`** | `96.8%` | `792` | `900` |
| **`SKU_EVAL_010`** | Accessories | `$182.62` | `595.8` | [465.9, 725.7] | **`624`** | `96.7%` | `570` | `654` |

---

## 7. Assumptions & Operating Caveats
1. **Single-Period Assumption:** The model assumes the initial buy commitment covers the 8-week launch period without in-season reordering. For replenishing lines, $Q$ should be adapted to lead-time demand plus review period.
2. **No Censoring Correction:** Demand forecasts represent unconstrained customer appetite; actual retail sales may be lower if stockouts occur in specific stores.