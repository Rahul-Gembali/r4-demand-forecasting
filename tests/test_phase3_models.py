"""Unit tests for Phase 3 launch curve baselines and analogue retrieval engine."""

import numpy as np
import pandas as pd
import pytest

from src.models.analogue import AnalogueForecaster, AttributeSimilarityEngine
from src.models.baseline import FallbackLevel, LaunchCurveBaseline


@pytest.fixture
def sample_training_data() -> pd.DataFrame:
    """Creates synthetic training features across 3 categories with varying density."""
    records = []
    # Category 1: Apparel with 10 SKUs (dense)
    for i in range(1, 11):
        for w in range(1, 9):
            records.append({
                "sku_id": f"APP_{i}",
                "launch_week_age": w,
                "category": "Apparel",
                "subcategory": "Jackets",
                "units_sold": 50.0 + w * 2.0,
            })

    # Category 2: Electronics with 2 SKUs (sparse subcategory)
    for i in range(1, 3):
        for w in range(1, 9):
            records.append({
                "sku_id": f"ELEC_{i}",
                "launch_week_age": w,
                "category": "Electronics",
                "subcategory": "Drones",
                "units_sold": 10.0 + w,
            })

    return pd.DataFrame(records)


def test_baseline_hierarchical_fallback(sample_training_data: pd.DataFrame):
    # min_donor_skus = 5
    baseline = LaunchCurveBaseline(min_donor_skus=5, aggregation_method="median")
    baseline.fit(sample_training_data)

    # 1. Level 1: Apparel/Jackets has 10 SKUs (>= 5) -> CATEGORY_SUBCATEGORY
    res_dense = baseline.predict_sku(category="Apparel", subcategory="Jackets", sku_id="Q1")
    assert res_dense.fallback_level == FallbackLevel.CATEGORY_SUBCATEGORY
    assert res_dense.donor_sku_count == 10
    assert len(res_dense.weekly_forecast) == 8
    assert res_dense.weekly_forecast[0] == 52.0  # Median of 50 + 1*2 = 52

    # 2. Level 2: Electronics/Drones has only 2 SKUs (< 5), Electronics total has only 2 (< 5) -> GLOBAL
    res_sparse = baseline.predict_sku(category="Electronics", subcategory="Drones", sku_id="Q2")
    assert res_sparse.fallback_level == FallbackLevel.GLOBAL

    # 3. Level 3: Completely unseen category -> GLOBAL
    res_unknown = baseline.predict_sku(category="NoveltySpaceItems", subcategory="MoonDust", sku_id="Q3")
    assert res_unknown.fallback_level == FallbackLevel.GLOBAL
    assert res_unknown.donor_sku_count == 12  # 10 + 2 total SKUs


def test_baseline_non_negative_forecasts(sample_training_data: pd.DataFrame):
    baseline = LaunchCurveBaseline(min_donor_skus=1, aggregation_method="median")
    baseline.fit(sample_training_data)

    df_test = pd.DataFrame([
        {"sku_id": "TEST_1", "category": "Apparel", "subcategory": "Jackets"},
        {"sku_id": "TEST_2", "category": "Unseen", "subcategory": "Unseen"},
    ])
    df_preds = baseline.predict_dataframe(df_test)

    assert len(df_preds) == 16  # 2 SKUs * 8 weeks
    assert (df_preds["predicted_sales"] >= 0).all()
    assert set(df_preds["horizon_week"]) == set(range(1, 9))


def test_similarity_metric_properties():
    engine = AttributeSimilarityEngine()

    item_a = {
        "sku_id": "A",
        "category": "Apparel",
        "subcategory": "Jackets",
        "base_price": 100.0,
        "brand_tier": "Tier 1 National",
        "colour": "Black",
        "material": "Leather",
        "launch_month": 1,
        "has_marketing_support": True,
    }

    # 1. Identity: Similarity with itself is 1.0
    sim_self = engine.compute_pair_similarity(item_a, item_a)
    assert sim_self == pytest.approx(1.0)

    # 2. Symmetry
    item_b = {
        "sku_id": "B",
        "category": "Apparel",
        "subcategory": "Jackets",
        "base_price": 80.0,
        "brand_tier": "Tier 1 National",
        "colour": "Navy",
        "material": "Wool",
        "launch_month": 3,
        "has_marketing_support": False,
    }
    sim_ab = engine.compute_pair_similarity(item_a, item_b)
    sim_ba = engine.compute_pair_similarity(item_b, item_a)
    assert sim_ab == pytest.approx(sim_ba)
    assert 0.0 <= sim_ab <= 1.0


def test_top_k_analogue_retrieval_and_self_exclusion():
    engine = AttributeSimilarityEngine()

    donor_attrs = pd.DataFrame([
        {"sku_id": "SKU_1", "category": "Apparel", "subcategory": "Jackets", "base_price": 50.0, "brand_tier": "Tier 1 National", "colour": "Black", "material": "Cotton", "launch_month": 2, "has_marketing_support": True},
        {"sku_id": "SKU_2", "category": "Apparel", "subcategory": "Jackets", "base_price": 52.0, "brand_tier": "Tier 1 National", "colour": "Black", "material": "Cotton", "launch_month": 2, "has_marketing_support": True},
        {"sku_id": "SKU_3", "category": "Apparel", "subcategory": "T-Shirts", "base_price": 20.0, "brand_tier": "Tier 3 Value", "colour": "White", "material": "Polyester", "launch_month": 8, "has_marketing_support": False},
    ])
    donor_sales = pd.DataFrame([
        {"sku_id": "SKU_1", "launch_week_age": w, "units_sold": 100.0} for w in range(1, 9)
    ] + [
        {"sku_id": "SKU_2", "launch_week_age": w, "units_sold": 90.0} for w in range(1, 9)
    ] + [
        {"sku_id": "SKU_3", "launch_week_age": w, "units_sold": 20.0} for w in range(1, 9)
    ])

    engine.fit_candidates(donor_attrs, donor_sales)

    # Query with identical attributes to SKU_1, but excluding SKU_1
    query = donor_attrs.iloc[0].to_dict()
    matches = engine.retrieve_top_k(query, k=2, exclude_sku_id="SKU_1")

    # SKU_1 must NOT be in the retrieved matches
    matched_skus = [m.analogue_sku_id for m in matches]
    assert "SKU_1" not in matched_skus
    # SKU_2 should be the top match
    assert matched_skus[0] == "SKU_2"


def test_analogue_forecaster_weighting():
    engine = AttributeSimilarityEngine()

    donor_attrs = pd.DataFrame([
        {"sku_id": "D1", "category": "Apparel", "subcategory": "Jackets", "base_price": 100.0, "brand_tier": "Tier 1", "colour": "Black", "material": "Leather", "launch_month": 1, "has_marketing_support": True},
        {"sku_id": "D2", "category": "Apparel", "subcategory": "Jeans", "base_price": 50.0, "brand_tier": "Tier 2", "colour": "Blue", "material": "Denim", "launch_month": 6, "has_marketing_support": False},
    ])
    # D1 sells 100/wk, D2 sells 20/wk
    donor_sales = pd.DataFrame([
        {"sku_id": "D1", "launch_week_age": w, "units_sold": 100.0} for w in range(1, 9)
    ] + [
        {"sku_id": "D2", "launch_week_age": w, "units_sold": 20.0} for w in range(1, 9)
    ])
    engine.fit_candidates(donor_attrs, donor_sales)

    forecaster = AnalogueForecaster(engine, k=2, temperature_power=2.0)

    # Query matching D1 much closer than D2
    query = {"sku_id": "Q_JACKET", "category": "Apparel", "subcategory": "Jackets", "base_price": 95.0, "brand_tier": "Tier 1", "colour": "Black", "material": "Leather", "launch_month": 1, "has_marketing_support": True}
    res = forecaster.forecast_sku(query)

    assert len(res.weighted_forecast) == 8
    # Because query is much closer to D1 (100) than D2 (20), forecast should be close to 100
    assert res.weighted_forecast[0] > 80.0
    assert (np.array(res.weighted_forecast) >= 0).all()
