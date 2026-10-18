"""Unit tests for Phase 7 Forecast Explanations and Confidence Ranking."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.explainability.confidence import ConfidenceScorer, SKUConfidenceMetrics
from src.explainability.shap_engine import SKUFeatureContribution, TreeShapEngine
from src.explainability.synthesizer import CompleteSKUExplanation, ExplanationSynthesizer
from src.models.supervised import ColdStartPredictor


@pytest.fixture
def trained_predictor() -> ColdStartPredictor:
    artifact_path = Path("artifacts/models/supervised_coldstart_v1")
    return ColdStartPredictor.from_artifact(artifact_path)


def test_shap_engine_additivity(trained_predictor: ColdStartPredictor):
    shap_engine = TreeShapEngine(trained_predictor.forecaster)

    # 8-week synthetic SKU features
    records = []
    for w in range(1, 9):
        records.append({
            "sku_id": "TEST_SHAP_SKU",
            "launch_week_age": w,
            "category": "Footwear",
            "subcategory": "Sneakers",
            "colour": "Black",
            "material": "Leather",
            "brand": "CoreBrand",
            "brand_tier": "Tier 1 National",
            "price_band": "Mid-Range",
            "base_price": 99.0,
            "log_base_price": np.log1p(99.0),
            "launch_month": 4,
            "sin_launch_month": 0.866,
            "cos_launch_month": -0.5,
            "marketing_flag": 1 if w <= 4 else 0,
            "is_holiday_week": 0,
            "week_of_year": 14 + w,
            "sin_week_of_year": 0.2,
            "cos_week_of_year": 0.9,
        })
    df_sku_8w = pd.DataFrame(records)

    contrib: SKUFeatureContribution = shap_engine.explain_sku_weeks(df_sku_8w)

    # Validate exact additivity for week 1
    X = trained_predictor.forecaster.prepare_features(df_sku_8w)
    raw_pred_w1 = trained_predictor.forecaster.model.predict(X.iloc[[0]])[0]

    w1_shap_sum = sum(contrib.weekly_shap_values[0].values())
    reconstructed_pred = contrib.base_value + w1_shap_sum

    assert reconstructed_pred == pytest.approx(raw_pred_w1, rel=1e-3)
    assert len(contrib.positive_drivers) > 0 or len(contrib.negative_drivers) > 0


def test_confidence_scorer_bounds_and_tiering():
    scorer = ConfidenceScorer()

    # High confidence case: tight interval, close analogues, consensus, good category
    res_high = scorer.score_sku(
        sku_id="HIGH_CONF_SKU",
        category="Footwear",
        base_price=100.0,
        point_forecast_cumul=500.0,
        lower_bound_90_cumul=420.0,
        upper_bound_90_cumul=580.0,
        top_analogue_similarities=[0.95, 0.94, 0.93, 0.92, 0.91],
        analogue_forecast_cumul=510.0,
    )
    assert 0.0 <= res_high.composite_confidence_score <= 100.0
    assert res_high.confidence_tier == "HIGH"
    assert len(res_high.uncertainty_flags) == 0

    # Low confidence case: wide interval, distant analogues, high disagreement, price outlier
    res_low = scorer.score_sku(
        sku_id="LOW_CONF_SKU",
        category="Accessories",
        base_price=350.0,  # extreme price outlier
        point_forecast_cumul=200.0,
        lower_bound_90_cumul=50.0,
        upper_bound_90_cumul=400.0,  # very wide interval (width 350 / 200 = 175%)
        top_analogue_similarities=[0.65, 0.62, 0.60, 0.58, 0.55],
        analogue_forecast_cumul=380.0,  # high disagreement
        category_price_mean=80.0,
        category_price_std=30.0,
    )
    assert 0.0 <= res_low.composite_confidence_score <= 100.0
    assert res_low.confidence_tier == "LOW"
    assert "WIDE_PREDICTION_INTERVAL" in res_low.uncertainty_flags
    assert "DISTANT_OR_SPARSE_ANALOGUES" in res_low.uncertainty_flags
    assert "HIGH_MODEL_DISAGREEMENT" in res_low.uncertainty_flags
    assert "EXTREME_PRICE_OUTLIER" in res_low.uncertainty_flags


def test_narrow_vs_wide_interval_impact():
    scorer = ConfidenceScorer()

    # Fixed base parameters
    args = {
        "sku_id": "TEST_INTERVAL",
        "category": "Apparel",
        "base_price": 75.0,
        "point_forecast_cumul": 400.0,
        "top_analogue_similarities": [0.90, 0.89, 0.88],
        "analogue_forecast_cumul": 405.0,
    }

    # Narrow interval: [350, 450] (width = 100)
    res_narrow = scorer.score_sku(
        **args,
        lower_bound_90_cumul=350.0,
        upper_bound_90_cumul=450.0,
    )

    # Wide interval: [200, 600] (width = 400)
    res_wide = scorer.score_sku(
        **args,
        lower_bound_90_cumul=200.0,
        upper_bound_90_cumul=600.0,
    )

    assert res_narrow.composite_confidence_score > res_wide.composite_confidence_score
    assert res_narrow.sub_scores["interval_spread"] > res_wide.sub_scores["interval_spread"]


def test_analogue_distance_impact():
    scorer = ConfidenceScorer()
    args = {
        "sku_id": "TEST_ANA",
        "category": "Home",
        "base_price": 80.0,
        "point_forecast_cumul": 300.0,
        "lower_bound_90_cumul=240.0": 240.0,
        "upper_bound_90_cumul=360.0": 360.0,
        "analogue_forecast_cumul": 300.0,
    }

    res_close = scorer.score_sku(
        sku_id="TEST_ANA_1",
        category="Home",
        base_price=80.0,
        point_forecast_cumul=300.0,
        lower_bound_90_cumul=240.0,
        upper_bound_90_cumul=360.0,
        top_analogue_similarities=[0.96, 0.95, 0.94],
        analogue_forecast_cumul=300.0,
    )

    res_distant = scorer.score_sku(
        sku_id="TEST_ANA_2",
        category="Home",
        base_price=80.0,
        point_forecast_cumul=300.0,
        lower_bound_90_cumul=240.0,
        upper_bound_90_cumul=360.0,
        top_analogue_similarities=[0.68, 0.65, 0.62],
        analogue_forecast_cumul=300.0,
    )

    assert res_close.composite_confidence_score > res_distant.composite_confidence_score
    assert res_close.sub_scores["analogue_quality"] > res_distant.sub_scores["analogue_quality"]


def test_invalid_weights_validation():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        ConfidenceScorer(weights={"w1": 0.5, "w2": 0.2})


def test_explanation_synthesis_no_causality():
    scorer = ConfidenceScorer()
    conf = scorer.score_sku(
        sku_id="SKU_NO_CAUSAL",
        category="Apparel",
        base_price=49.99,
        point_forecast_cumul=250.0,
        lower_bound_90_cumul=180.0,
        upper_bound_90_cumul=320.0,
        top_analogue_similarities=[0.88, 0.86],
    )

    fake_contrib = SKUFeatureContribution(
        sku_id="SKU_NO_CAUSAL",
        base_value=4.5,
        cumulative_shap_values={"base_price": -0.2, "category": 0.4},
        weekly_shap_values=[],
        positive_drivers=[("category", 0.4)],
        negative_drivers=[("base_price", -0.2)],
    )

    explanation = ExplanationSynthesizer.synthesize_explanation(
        sku_attr={"sku_id": "SKU_NO_CAUSAL", "category": "Apparel", "base_price": 49.99},
        weekly_forecast=[30.0] * 8,
        cumul_forecast=240.0,
        interval_80=(190.0, 290.0),
        interval_90=(170.0, 310.0),
        confidence_metrics=conf,
        shap_contributions=fake_contrib,
        top_analogues=[],
        baseline_info={"hierarchy_level": "CATEGORY", "donor_sku_count": 300},
    )

    summary = explanation.human_readable_summary
    # Disclaimers must be present
    assert "Note:" in summary or "TreeSHAP" in summary
    assert "causality" in summary.lower()
    # No false certainty claim
    assert "guaranteed" not in summary.lower()
    assert "causes" not in summary.lower()


def test_least_confident_skus_file_integrity():
    least_path = Path("data/processed/least_confident_10_skus.csv")
    assert least_path.exists(), "least_confident_10_skus.csv must exist."

    df = pd.read_csv(least_path)
    assert len(df) == 10
    # Scores must be sorted ascending
    scores = df["confidence_score"].tolist()
    assert scores == sorted(scores)
    assert all(0.0 <= s <= 100.0 for s in scores)
