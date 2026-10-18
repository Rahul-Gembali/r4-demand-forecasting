"""Confidence Scoring & Ranking Engine for Cold-Start Retail SKUs.

Computes a transparent, multi-indicator Cold-Start Confidence Index in [0.0, 100.0]
derived from prediction interval width, analogue similarity, model consensus,
historical category track record, and product attribute typicality.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class SKUConfidenceMetrics:
    """Detailed diagnostic confidence breakdown for a single SKU."""
    sku_id: str
    composite_confidence_score: float      # Final score in [0.0, 100.0]
    confidence_tier: str                   # 'HIGH' (>=75), 'MEDIUM' (60-74), 'LOW' (<60)
    relative_interval_width: float        # (Upper90 - Lower90) / PointForecast
    mean_analogue_similarity: float       # Average similarity of top-5 analogues
    model_divergence_pct: float           # |Supervised - Analogue| / Supervised * 100%
    category_historical_wape: float       # Validation/Test WAPE for category
    price_z_score: float                  # Standardized price relative to category peers
    sub_scores: dict[str, float]          # Normalized sub-scores in [0.0, 1.0]
    uncertainty_flags: list[str]          # Actionable reason codes for low confidence


class ConfidenceScorer:
    """Computes transparent Cold-Start Confidence Scores without probability mislabeling."""

    DEFAULT_WEIGHTS = {
        "interval_spread": 0.30,
        "analogue_quality": 0.25,
        "model_consensus": 0.20,
        "category_track_record": 0.15,
        "attribute_typicality": 0.10,
    }

    # Empirical category error benchmarks from Phase 5 official holdout evaluation
    CATEGORY_WAPE_BENCHMARKS = {
        "Footwear": 0.2461,
        "Apparel": 0.2543,
        "Home": 0.2604,
        "Accessories": 0.2672,
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        total_w = sum(self.weights.values())
        if not math_isclose(total_w, 1.0, abs_tol=1e-4):
            raise ValueError(f"Confidence component weights must sum to 1.0, got {total_w}")

    def score_sku(
        self,
        sku_id: str,
        category: str,
        base_price: float,
        point_forecast_cumul: float,
        lower_bound_90_cumul: float,
        upper_bound_90_cumul: float,
        top_analogue_similarities: list[float],
        analogue_forecast_cumul: float | None = None,
        category_price_mean: float = 120.0,
        category_price_std: float = 40.0,
        has_novel_attributes: bool = False,
    ) -> SKUConfidenceMetrics:
        """Calculates normalized confidence indicators and composite score."""
        mu = max(1.0, float(point_forecast_cumul))
        lb90 = max(0.0, float(lower_bound_90_cumul))
        ub90 = max(lb90, float(upper_bound_90_cumul))
        uncertainty_flags = []

        # 1. Relative Interval Width Sub-Score
        # Calibrated 90% conformal width is typically ~0.45 of demand
        interval_width = ub90 - lb90
        rel_width = interval_width / mu
        # Score = 1.0 if rel_width <= 0.30; 0.0 if rel_width >= 0.90
        s_interval = 1.0 - float(np.clip((rel_width - 0.30) / (0.90 - 0.30), 0.0, 1.0))
        if rel_width > 0.65:
            uncertainty_flags.append("WIDE_PREDICTION_INTERVAL")

        # 2. Analogue Quality Sub-Score
        sims = top_analogue_similarities if top_analogue_similarities else [0.5]
        mean_sim = float(np.mean(sims))
        # Score = 1.0 if mean_sim >= 0.92; 0.0 if mean_sim <= 0.70
        s_analogue = float(np.clip((mean_sim - 0.70) / (0.92 - 0.70), 0.0, 1.0))
        if mean_sim < 0.82:
            uncertainty_flags.append("DISTANT_OR_SPARSE_ANALOGUES")

        # 3. Model Consensus Sub-Score (Supervised vs Analogue Retrieval)
        if analogue_forecast_cumul is not None and analogue_forecast_cumul > 0.0:
            divergence = abs(mu - float(analogue_forecast_cumul)) / mu
            divergence_pct = divergence * 100.0
            # Score = 1.0 if divergence <= 0.05; 0.0 if divergence >= 0.40
            s_consensus = 1.0 - float(np.clip((divergence - 0.05) / (0.40 - 0.05), 0.0, 1.0))
            if divergence > 0.25:
                uncertainty_flags.append("HIGH_MODEL_DISAGREEMENT")
        else:
            divergence_pct = 0.0
            s_consensus = 0.70

        # 4. Category Track Record Sub-Score
        cat_wape = self.CATEGORY_WAPE_BENCHMARKS.get(category, 0.2800)
        # Score = 1.0 if wape <= 0.22; 0.0 if wape >= 0.32
        s_category = 1.0 - float(np.clip((cat_wape - 0.22) / (0.32 - 0.22), 0.0, 1.0))
        if cat_wape > 0.265:
            uncertainty_flags.append("HISTORICALLY_VOLATILE_CATEGORY")

        # 5. Attribute Typicality Sub-Score (Price Z-score & Novelty)
        std_safe = max(5.0, category_price_std)
        z_price = abs(float(base_price) - category_price_mean) / std_safe
        s_price = 1.0 - float(np.clip((z_price - 1.0) / (3.0 - 1.0), 0.0, 1.0))
        if has_novel_attributes:
            s_price *= 0.60
            uncertainty_flags.append("UNSEEN_OR_RARE_ATTRIBUTES")
        if z_price > 2.2:
            uncertainty_flags.append("EXTREME_PRICE_OUTLIER")

        s_typicality = float(np.clip(s_price, 0.0, 1.0))

        sub_scores = {
            "interval_spread": round(s_interval, 4),
            "analogue_quality": round(s_analogue, 4),
            "model_consensus": round(s_consensus, 4),
            "category_track_record": round(s_category, 4),
            "attribute_typicality": round(s_typicality, 4),
        }

        # Weighted combination scaled to 0-100
        composite_score = sum(sub_scores[k] * self.weights[k] for k in self.weights) * 100.0
        composite_score = round(float(np.clip(composite_score, 0.0, 100.0)), 2)

        if composite_score >= 75.0:
            tier = "HIGH"
        elif composite_score >= 60.0:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        return SKUConfidenceMetrics(
            sku_id=sku_id,
            composite_confidence_score=composite_score,
            confidence_tier=tier,
            relative_interval_width=round(rel_width, 4),
            mean_analogue_similarity=round(mean_sim, 4),
            model_divergence_pct=round(divergence_pct, 2),
            category_historical_wape=round(cat_wape, 4),
            price_z_score=round(z_price, 2),
            sub_scores=sub_scores,
            uncertainty_flags=uncertainty_flags,
        )


def math_isclose(a: float, b: float, abs_tol: float = 1e-4) -> bool:
    return abs(a - b) <= abs_tol
