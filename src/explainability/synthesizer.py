"""Forecast Explanation Synthesizer for Cold-Start Retail SKUs.

Integrates TreeSHAP feature contributions, historical analogue evidence,
category baseline fallbacks, business-rule adjustments, confidence scores,
and non-causal human-readable prose synthesis.
"""

from dataclasses import dataclass
from typing import Any

from src.explainability.confidence import SKUConfidenceMetrics
from src.explainability.shap_engine import SKUFeatureContribution


@dataclass
class CompleteSKUExplanation:
    """Consolidated explanation artifact for a single new SKU forecast."""
    sku_id: str
    product_name: str
    category: str
    subcategory: str
    base_price: float
    model_version: str
    forecast_cumulative_8w: float
    weekly_forecast_8w: list[float]
    prediction_interval_80: tuple[float, float]
    prediction_interval_90: tuple[float, float]
    confidence_score: float
    confidence_tier: str
    uncertainty_flags: list[str]
    top_analogues: list[dict[str, Any]]
    category_baseline_explanation: dict[str, Any]
    shap_positive_drivers: list[tuple[str, float]]
    shap_negative_drivers: list[tuple[str, float]]
    business_rule_adjustments: dict[str, Any]
    human_readable_summary: str
    suggested_review_checks: list[str]


class ExplanationSynthesizer:
    """Synthesizes comprehensive, auditable, and non-causal forecast explanations."""

    @classmethod
    def synthesize_explanation(
        cls,
        sku_attr: dict[str, Any],
        weekly_forecast: list[float],
        cumul_forecast: float,
        interval_80: tuple[float, float],
        interval_90: tuple[float, float],
        confidence_metrics: SKUConfidenceMetrics,
        shap_contributions: SKUFeatureContribution,
        top_analogues: list[dict[str, Any]],
        baseline_info: dict[str, Any],
        model_version: str = "v1.0.0-catboost",
    ) -> CompleteSKUExplanation:
        """Synthesizes all explanation signals into a unified audit record."""
        sku_id = str(sku_attr.get("sku_id", "NEW_SKU"))
        p_name = str(sku_attr.get("product_name", f"Product {sku_id}"))
        category = str(sku_attr.get("category", "General"))
        subcategory = str(sku_attr.get("subcategory", "General"))
        base_price = float(sku_attr.get("base_price", 49.99))
        has_mkt = bool(sku_attr.get("has_marketing_support", False))

        # 1. Business-rule adjustments
        business_rules = {
            "marketing_support_flag": "Active in introductory weeks 1-4; deactivated in weeks 5-8" if has_mkt else "Inactive",
            "non_negativity_truncation": "Applied (all predicted weekly values clamped to >= 0.0)",
            "single_period_newsvendor_alignment": "Uncertainty intervals derived from calibrated 8-week cumulative non-conformity",
        }

        # 2. Suggested commercial review checks based on uncertainty flags
        suggested_checks = []
        if "WIDE_PREDICTION_INTERVAL" in confidence_metrics.uncertainty_flags:
            suggested_checks.append("Demand dispersion is high; recommend placing split order with in-season reorder option.")
        if "DISTANT_OR_SPARSE_ANALOGUES" in confidence_metrics.uncertainty_flags:
            suggested_checks.append("Few close historical matches; conduct qualitative merchandising review of attribute positioning.")
        if "HIGH_MODEL_DISAGREEMENT" in confidence_metrics.uncertainty_flags:
            suggested_checks.append("Supervised GBDT and analogue retrieval diverge; inspect price elasticity and promotional timing.")
        if "EXTREME_PRICE_OUTLIER" in confidence_metrics.uncertainty_flags:
            suggested_checks.append("Product price lies outside category interquartile range; confirm MSRP positioning.")
        if not suggested_checks:
            suggested_checks.append("Confidence is high; proceed with standard operational purchase schedule.")

        # 3. Construct non-causal human-readable prose summary
        top_pos = [f"'{feat}' (+{val:.2f})" for feat, val in shap_contributions.positive_drivers[:2]]
        top_neg = [f"'{feat}' ({val:.2f})" for feat, val in shap_contributions.negative_drivers[:2]]

        pos_text = f"Primary positive empirical drivers include {', '.join(top_pos)}." if top_pos else "No strong positive drivers."
        neg_text = f"Primary downward empirical drivers include {', '.join(top_neg)}." if top_neg else "No strong negative drivers."

        top_ana_text = ""
        if top_analogues:
            best_ana = top_analogues[0]
            top_ana_text = (
                f" The closest historical analogue is {best_ana.get('analogue_sku_id', 'N/A')} "
                f"(similarity: {best_ana.get('similarity_score', 0.0):.3f}, "
                f"observed 8-week sales: {sum(best_ana.get('observed_curve', [0])):,.0f} units)."
            )

        summary_prose = (
            f"SKU '{sku_id}' ({p_name}) in '{category} / {subcategory}' is forecasted to achieve "
            f"{cumul_forecast:,.1f} units over its initial 8-week launch period "
            f"(90% prediction interval: [{interval_90[0]:,.1f}, {interval_90[1]:,.1f}] units). "
            f"The Cold-Start Confidence Index is {confidence_metrics.composite_confidence_score:.1f}/100 "
            f"({confidence_metrics.confidence_tier} confidence). {pos_text} {neg_text}"
            f"{top_ana_text} Note: TreeSHAP contributions represent statistical associations learned "
            f"from historical mature launches and do not imply direct business causality."
        )

        return CompleteSKUExplanation(
            sku_id=sku_id,
            product_name=p_name,
            category=category,
            subcategory=subcategory,
            base_price=base_price,
            model_version=model_version,
            forecast_cumulative_8w=round(cumul_forecast, 2),
            weekly_forecast_8w=[round(x, 2) for x in weekly_forecast],
            prediction_interval_80=(round(interval_80[0], 2), round(interval_80[1], 2)),
            prediction_interval_90=(round(interval_90[0], 2), round(interval_90[1], 2)),
            confidence_score=confidence_metrics.composite_confidence_score,
            confidence_tier=confidence_metrics.confidence_tier,
            uncertainty_flags=confidence_metrics.uncertainty_flags,
            top_analogues=top_analogues[:5],
            category_baseline_explanation=baseline_info,
            shap_positive_drivers=shap_contributions.positive_drivers,
            shap_negative_drivers=shap_contributions.negative_drivers,
            business_rule_adjustments=business_rules,
            human_readable_summary=summary_prose,
            suggested_review_checks=suggested_checks,
        )
