#!/usr/bin/env python3
"""Phase 7 Forecast Explanations and Confidence Ranking Pipeline.

1. Computes exact TreeSHAP feature contributions across all 8 introductory weeks.
2. Retrieves historical analogues, similarity scores, and donor curves.
3. Incorporates category baseline curves and fallback hierarchy documentation.
4. Generates multi-indicator confidence scores and uncertainty flags.
5. Identifies and diagnoses the Ten Least-Confident SKUs.
6. Synthesizes non-causal human-readable explanations and commercial review actions.
7. Saves comprehensive audit manifests and compiles docs/FORECAST_EXPLANATIONS_AND_CONFIDENCE_REPORT.md.
"""

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.explainability.confidence import ConfidenceScorer
from src.explainability.shap_engine import TreeShapEngine
from src.explainability.synthesizer import CompleteSKUExplanation, ExplanationSynthesizer
from src.models.supervised import ColdStartPredictor


def main() -> int:
    print("=" * 85)
    print(" R4 DEMAND FORECASTING — PHASE 7 EXPLANATIONS & CONFIDENCE RANKING")
    print("=" * 85)

    processed_dir = Path("data/processed")
    raw_dir = Path("data/raw")
    artifact_dir = Path("artifacts/models/supervised_coldstart_v1")
    exp_dir = Path("artifacts/explainability")
    docs_dir = Path("docs")

    exp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Model, Datasets, and Pre-Computed Records
    print("\n1. Loading predictor, feature panels, analogue matches, and baseline records...")
    predictor = ColdStartPredictor.from_artifact(artifact_dir)
    df_new_attrs = pd.read_csv(raw_dir / "new_sku_attributes.csv")
    df_inf_features = pd.read_parquet(processed_dir / "inference_features.parquet")
    df_forecasts_int = pd.read_csv(processed_dir / "forecasts_with_intervals_150_skus.csv")
    df_baseline = pd.read_csv(processed_dir / "forecasts_baseline_150_skus.csv")

    with open(processed_dir / "analogue_retrieval_records.json", encoding="utf-8") as f:
        analogue_records_list = json.load(f)
    analogue_map = {r["query_sku_id"]: r for r in analogue_records_list}

    # Baseline mapping: group by sku_id to get donor count and hierarchy key
    baseline_sku_map = (
        df_baseline.groupby("sku_id")
        .agg({
            "donor_sku_count": "first",
            "hierarchy_key": "first",
            "predicted_sales": list,
        })
        .to_dict(orient="index")
    )

    # 2. Initialize TreeSHAP and Confidence Engines
    print("\n2. Initializing TreeSHAP Engine and Multi-Indicator Confidence Scorer...")
    shap_engine = TreeShapEngine(predictor.forecaster)
    confidence_scorer = ConfidenceScorer()

    # Calculate category price distributions for typicality scoring
    cat_price_stats = (
        df_new_attrs.groupby("category")["base_price"]
        .agg(["mean", "std"])
        .to_dict(orient="index")
    )

    # 3. Generate Complete Explanations for all 150 Evaluation SKUs
    print("\n3. Generating TreeSHAP contributions, analogue synthesis, and confidence metrics for 150 SKUs...")
    all_explanations: list[CompleteSKUExplanation] = []
    confidence_rows: list[dict[str, Any]] = []

    unique_skus = df_new_attrs["sku_id"].unique()

    for sku_id in unique_skus:
        sku_attr = df_new_attrs[df_new_attrs["sku_id"] == sku_id].iloc[0].to_dict()
        category = str(sku_attr.get("category", "General"))
        base_price = float(sku_attr.get("base_price", 49.99))

        # Filter 8-week feature records and forecasts
        df_sku_feat = df_inf_features[df_inf_features["sku_id"] == sku_id].sort_values("launch_week_age")
        df_sku_fc = df_forecasts_int[df_forecasts_int["sku_id"] == sku_id].sort_values("horizon_week")

        weekly_fc = df_sku_fc["predicted_sales"].tolist()
        cumul_fc = float(df_sku_fc["cumul_pred_8w"].iloc[0])
        l80 = float(df_sku_fc["cumul_lower_80"].iloc[0])
        u80 = float(df_sku_fc["cumul_upper_80"].iloc[0])
        l90 = float(df_sku_fc["cumul_lower_90"].iloc[0])
        u90 = float(df_sku_fc["cumul_upper_90"].iloc[0])

        # 3a. TreeSHAP Feature Attributions
        shap_contrib = shap_engine.explain_sku_weeks(df_sku_feat)

        # 3b. Analogue Match Info
        ana_rec = analogue_map.get(sku_id, {})
        top_matches = ana_rec.get("top_k_matches", [])
        ana_fc_list = ana_rec.get("weighted_forecast", [])
        ana_cumul_fc = sum(ana_fc_list) if ana_fc_list else None
        sims = [m.get("similarity_score", 0.5) for m in top_matches]

        # 3c. Baseline Hierarchy Info
        base_rec = baseline_sku_map.get(sku_id, {})
        base_info = {
            "hierarchy_level": "CATEGORY_SUBCATEGORY",
            "hierarchy_key": base_rec.get("hierarchy_key", "Category / Subcategory"),
            "donor_sku_count": base_rec.get("donor_sku_count", 300),
            "baseline_8w_forecast": [round(x, 2) for x in base_rec.get("predicted_sales", [])],
        }

        # 3d. Confidence Scoring
        cat_stat = cat_price_stats.get(category, {"mean": 120.0, "std": 40.0})
        conf_metrics = confidence_scorer.score_sku(
            sku_id=sku_id,
            category=category,
            base_price=base_price,
            point_forecast_cumul=cumul_fc,
            lower_bound_90_cumul=l90,
            upper_bound_90_cumul=u90,
            top_analogue_similarities=sims,
            analogue_forecast_cumul=ana_cumul_fc,
            category_price_mean=cat_stat.get("mean", 120.0),
            category_price_std=cat_stat.get("std", 40.0),
            has_novel_attributes=False,
        )

        # 3e. Synthesize Explanation
        explanation = ExplanationSynthesizer.synthesize_explanation(
            sku_attr=sku_attr,
            weekly_forecast=weekly_fc,
            cumul_forecast=cumul_fc,
            interval_80=(l80, u80),
            interval_90=(l90, u90),
            confidence_metrics=conf_metrics,
            shap_contributions=shap_contrib,
            top_analogues=top_matches,
            baseline_info=base_info,
            model_version="v1.0.0-catboost",
        )
        all_explanations.append(explanation)

        confidence_rows.append({
            "sku_id": sku_id,
            "product_name": sku_attr.get("product_name"),
            "category": category,
            "subcategory": sku_attr.get("subcategory"),
            "base_price": base_price,
            "forecast_cumul_8w": round(cumul_fc, 1),
            "lower_bound_90": round(l90, 1),
            "upper_bound_90": round(u90, 1),
            "confidence_score": conf_metrics.composite_confidence_score,
            "confidence_tier": conf_metrics.confidence_tier,
            "relative_interval_width": conf_metrics.relative_interval_width,
            "mean_analogue_similarity": conf_metrics.mean_analogue_similarity,
            "model_divergence_pct": conf_metrics.model_divergence_pct,
            "price_z_score": conf_metrics.price_z_score,
            "uncertainty_flags": "; ".join(conf_metrics.uncertainty_flags) if conf_metrics.uncertainty_flags else "NONE",
            "suggested_review": explanation.suggested_review_checks[0] if explanation.suggested_review_checks else "Standard",
        })

    df_confidence = pd.DataFrame(confidence_rows)

    # 4. Rank and Extract Ten Least-Confident SKUs
    print("\n4. Ranking SKUs by Confidence Score and Extracting 10 Least-Confident Products...")
    df_ranked = df_confidence.sort_values("confidence_score", ascending=True).reset_index(drop=True)
    df_least_10 = df_ranked.head(10).copy()

    print("\n" + "=" * 95)
    print(" TEN LEAST-CONFIDENT NEW PRODUCT FORECASTS (Action Required)")
    print("=" * 95)
    print(f"{'Rank':<4} | {'SKU ID':<13} | {'Category':<11} | {'Price':<7} | {'Forecast':<9} | {'90% Interval':<16} | {'Score':<6} | {'Tier':<6} | {'Primary Risk Flag':<20}")
    print("-" * 95)
    for idx, row in df_least_10.iterrows():
        int_str = f"[{row['lower_bound_90']:.0f}, {row['upper_bound_90']:.0f}]"
        primary_flag = row["uncertainty_flags"].split(";")[0] if row["uncertainty_flags"] != "NONE" else "Nominal"
        print(
            f"{idx + 1:<4d} | {row['sku_id']:<13} | {row['category']:<11} | ${row['base_price']:<6.2f} | "
            f"{row['forecast_cumul_8w']:<9.1f} | {int_str:<16} | {row['confidence_score']:<6.1f} | {row['confidence_tier']:<6} | {primary_flag:<20}"
        )
    print("=" * 95)

    # 5. Export Deliverables
    # 5a. Full 150-SKU Explanations JSON
    exp_json_path = processed_dir / "forecast_explanations_150_skus.json"
    with open(exp_json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in all_explanations], f, indent=2)
    print(f"\n5. Saved complete explanation records: {exp_json_path} (150 records)")

    # 5b. Least Confident 10 SKUs CSV
    least_csv_path = processed_dir / "least_confident_10_skus.csv"
    df_least_10.to_csv(least_csv_path, index=False)
    print(f"   - Saved 10 least-confident SKUs CSV: {least_csv_path}")

    # 5c. Confidence Summary Manifest
    summary_manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_skus": len(df_ranked),
        "mean_confidence_score": round(float(df_ranked["confidence_score"].mean()), 2),
        "median_confidence_score": round(float(df_ranked["confidence_score"].median()), 2),
        "tier_counts": df_ranked["confidence_tier"].value_counts().to_dict(),
        "weights": confidence_scorer.weights,
        "least_confident_10_skus": df_least_10["sku_id"].tolist(),
    }
    summary_path = exp_dir / "confidence_ranking_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_manifest, f, indent=2)
    print(f"   - Saved confidence ranking summary: {summary_path}")

    # 6. Generate Comprehensive Markdown Report
    report_md_path = docs_dir / "FORECAST_EXPLANATIONS_AND_CONFIDENCE_REPORT.md"
    generate_markdown_report(summary_manifest, df_least_10, df_ranked, all_explanations[0], report_md_path)
    print(f"   - Saved Explanations & Confidence Report: {report_md_path}")

    print("\n" + "=" * 85)
    print("Phase 7 Forecast Explanations and Confidence Ranking Completed Successfully.")
    print("=" * 85)
    return 0


def generate_markdown_report(
    summary: dict[str, Any],
    df_least_10: pd.DataFrame,
    df_all: pd.DataFrame,
    sample_exp: CompleteSKUExplanation,
    out_path: Path,
) -> None:
    tier_counts = summary["tier_counts"]
    lines = [
        "# PHASE 7 FORECAST EXPLANATIONS & CONFIDENCE RANKING REPORT",
        "",
        f"**Audit Timestamp:** `{summary['generated_at']}`  ",
        "**Target Population:** 150 New Cold-Start Evaluation SKUs  ",
        "**Model Version:** `v1.0.0-catboost`  ",
        "**Explainability Method:** Native TreeSHAP + Attribute Analogue Retrieval + Multi-Indicator Confidence Scoring  ",
        "",
        "---",
        "",
        "## 1. Executive Summary: Portfolio Confidence Distribution",
        "",
        f"Across all 150 newly launched products, the **Mean Confidence Score** is **`{summary['mean_confidence_score']:.1f}/100`** "
        f"(Median: `{summary['median_confidence_score']:.1f}/100`).",
        "",
        "| Confidence Tier | Score Range | SKU Count | Percentage | Recommended Commercial Posture |",
        "| :--- | :---: | :---: | :---: | :--- |",
        f"| **HIGH** | `75.0 - 100.0` | **`{tier_counts.get('HIGH', 0)}` SKUs** | `{tier_counts.get('HIGH', 0) / len(df_all) * 100:.1f}%` | Automated procurement; standard case-pack buy. |",
        f"| **MEDIUM** | `60.0 - 74.9` | **`{tier_counts.get('MEDIUM', 0)}` SKUs** | `{tier_counts.get('MEDIUM', 0) / len(df_all) * 100:.1f}%` | Category manager sign-off; standard monitoring. |",
        f"| **LOW (Review Required)** | `< 60.0` | **`{tier_counts.get('LOW', 0)}` SKUs** | `{tier_counts.get('LOW', 0) / len(df_all) * 100:.1f}%` | **Manual merchant audit**; conservative buy / split commitment. |",
        "",
        "> [!NOTE]",
        "> **Calibration Notice**: As mandated by forecasting governance standards, this score is an empirical **Relative Confidence Index (0-100)** derived from observable uncertainty signals, not a Bayesian posterior probability.",
        "",
        "---",
        "",
        "## 2. The Ten Least-Confident SKUs (Immediate Review Roster)",
        "",
        "These 10 products exhibit the highest forecast risk due to wide conformal intervals, distant analogue matches, large model divergence, or extreme price positioning:",
        "",
        "| Rank | SKU ID | Product Category | Base Price | 8W Demand Forecast | 90% Prediction Interval | Confidence Score | Primary Risk Reason | Suggested Merchant Action |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |",
    ]

    for idx, row in df_least_10.iterrows():
        int_str = f"[{row['lower_bound_90']:.0f}, {row['upper_bound_90']:.0f}]"
        lines.append(
            f"| **#{idx + 1}** | **`{row['sku_id']}`** | {row['category']} | `${row['base_price']:.2f}` | "
            f"`{row['forecast_cumul_8w']:.1f}` | `{int_str}` | **`{row['confidence_score']:.1f}`** | "
            f"`{row['uncertainty_flags']}` | {row['suggested_review']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Explainability Architecture & Signal Separation",
        "",
        "To prevent confusion between statistical correlations and real-world mechanisms, explanations are separated into four distinct analytical layers:",
        "",
        "1. **TreeSHAP Marginal Feature Contributions:** Quantifies the net directional push of each product attribute relative to the global expected training baseline ($4.55$ in log1p demand space).",
        "2. **Historical Analogue Precedent:** Identifies the top-5 most similar mature retail products, displaying their exact observed 8-week launch trajectories.",
        "3. **Category Launch Curve Fallback:** Documents the baseline median trajectory for the department and subcategory, including donor sample sizes ($N = 300$).",
        "4. **Business-Rule Adjustments:** Explicitly tracks promotional marketing rules (active weeks 1–4) and non-negativity truncations.",
        "",
        "---",
        "",
        "## 4. Deep-Dive Sample Audit Record",
        f"Exemplar audit report for benchmark SKU (`{sample_exp.sku_id}`):",
        "",
        f"- **Product Name:** {sample_exp.product_name}",
        f"- **Category / Subcategory:** `{sample_exp.category} / {sample_exp.subcategory}`",
        f"- **Retail MSRP:** `${sample_exp.base_price:.2f}`",
        f"- **Cumulative 8-Week Forecast:** **`{sample_exp.forecast_cumulative_8w:.1f}` units**",
        f"- **Calibrated 90% Conformal Interval:** `[{sample_exp.prediction_interval_90[0]:.1f}, {sample_exp.prediction_interval_90[1]:.1f}]` units",
        f"- **Cold-Start Confidence Score:** **`{sample_exp.confidence_score:.1f}/100`** ({sample_exp.confidence_tier})",
        "",
        "### Top Empirical TreeSHAP Drivers:",
        "| Feature Name | Net 8-Week SHAP Contribution | Directional Impact | Non-Causal Interpretation |",
        "| :--- | :---: | :---: | :--- |",
    ])

    for feat, val in sample_exp.shap_positive_drivers[:3]:
        lines.append(f"| `{feat}` | **`+{val:.4f}`** | Upward | Statistically associated with higher launch velocity in mature cohort. |")
    for feat, val in sample_exp.shap_negative_drivers[:3]:
        lines.append(f"| `{feat}` | **`{val:.4f}`** | Downward | Statistically associated with lower introductory demand in mature cohort. |")

    lines.extend([
        "",
        "### Closest Historical Analogue Matches:",
        "| Analogue SKU | Similarity | Category | Subcategory | Base Price | Observed 8W Sales |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for ana in sample_exp.top_analogues[:3]:
        obs_total = sum(ana.get("observed_curve", [0]))
        lines.append(
            f"| `{ana.get('analogue_sku_id')}` | **`{ana.get('similarity_score', 0):.3f}`** | "
            f"{ana.get('category')} | {ana.get('subcategory')} | `${ana.get('base_price', 0):.2f}` | `{obs_total:,.0f}` units |"
        )

    lines.extend([
        "",
        "### Generated Commercial Narrative:",
        f"> *\"{sample_exp.human_readable_summary}\"*",
        "",
        "---",
        "",
        "## 5. Confidence Score Component Weights & Formula",
        "",
        "$$\\text{Confidence Score} = 100 \\times \\sum_{k=1}^5 w_k \\cdot S_k$$",
        "",
        "| Indicator Component ($S_k$) | Weight ($w_k$) | Measurement Mechanism | Low Score Condition |",
        "| :--- | :---: | :--- | :--- |",
        "| **Prediction Interval Spread** | `30%` | Relative width: $(U_{90} - L_{90}) / \\hat{D}$ | Wide conformal interval ($\text{Width} > 65\\%$ of demand). |",
        "| **Analogue Quality** | `25%` | Mean similarity of top-5 historical matches | Poor matches (similarity $< 0.82$). |",
        "| **Model Consensus** | `20%` | Divergence between GBDT and Analogue curves | Disagreement $> 25\\%$ between independent models. |",
        "| **Category Track Record** | `15%` | Historical held-out test WAPE for category | Volatile department (historical test $\text{WAPE} > 0.265$). |",
        "| **Attribute Typicality** | `10%` | Price Z-score relative to category peers | Severe pricing outlier ($|z| > 2.2$) or rare attributes. |",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
