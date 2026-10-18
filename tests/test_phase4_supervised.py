"""Unit tests for Phase 4 Supervised LightGBM Demand Forecasting Engine."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.models.supervised import (
    ColdStartPredictor,
    DatasetSplits,
    LightGBMForecaster,
    SKUWeeklyForecast,
    SupervisedDatasetBuilder,
)


@pytest.fixture
def sample_sku_week_df() -> pd.DataFrame:
    """Creates synthetic SKU-Week enterprise panel across 12 SKUs."""
    records = []
    categories = ["Apparel", "Footwear", "Accessories"]
    for i in range(1, 13):
        cat = categories[i % len(categories)]
        for w in range(1, 9):
            records.append({
                "sku_id": f"SKU_{i:02d}",
                "launch_week_age": w,
                "category": cat,
                "subcategory": f"{cat}_Sub",
                "colour": "Black",
                "material": "Cotton",
                "brand": "CoreBrand",
                "brand_tier": "Tier 1 National",
                "price_band": "Mid-Range",
                "base_price": 45.0,
                "log_base_price": np.log1p(45.0),
                "launch_month": 3,
                "sin_launch_month": 1.0,
                "cos_launch_month": 0.0,
                "marketing_flag": 1 if w <= 4 else 0,
                "is_holiday_week": 0,
                "week_of_year": 10 + w,
                "sin_week_of_year": 0.5,
                "cos_week_of_year": 0.8,
                "units_sold": 50.0 + (i * 2.0) - (w * 1.5),
            })
    return pd.DataFrame(records)


def test_sku_level_split_disjointness(sample_sku_week_df: pd.DataFrame):
    builder = SupervisedDatasetBuilder(random_seed=42)
    splits: DatasetSplits = builder.split_by_sku(sample_sku_week_df, train_ratio=0.5, val_ratio=0.25, test_ratio=0.25)

    train_skus = set(splits.train_skus)
    val_skus = set(splits.val_skus)
    test_skus = set(splits.test_skus)

    # 1. Strict pairwise disjointness
    assert train_skus.isdisjoint(val_skus)
    assert train_skus.isdisjoint(test_skus)
    assert val_skus.isdisjoint(test_skus)

    # 2. Complete coverage
    all_skus = set(sample_sku_week_df["sku_id"].unique())
    assert train_skus.union(val_skus).union(test_skus) == all_skus

    # 3. Each SKU has all 8 weeks in its split
    for sku in train_skus:
        assert len(splits.df_train[splits.df_train["sku_id"] == sku]) == 8
    for sku in val_skus:
        assert len(splits.df_val[splits.df_val["sku_id"] == sku]) == 8
    for sku in test_skus:
        assert len(splits.df_test[splits.df_test["sku_id"] == sku]) == 8


def test_supervised_pipeline_fit_and_predict(sample_sku_week_df: pd.DataFrame):
    builder = SupervisedDatasetBuilder(random_seed=42)
    splits = builder.split_by_sku(sample_sku_week_df, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)

    forecaster = LightGBMForecaster(
        objective="regression_l1",
        target_transform="raw",
        n_estimators=50,
        learning_rate=0.1,
        random_seed=42,
    )
    forecaster.fit(splits.df_train, splits.df_val)

    preds = forecaster.predict(splits.df_test)

    assert len(preds) == len(splits.df_test)
    assert (preds >= 0.0).all()
    assert not np.isnan(preds).any()


def test_cold_start_predictor_single_sku(sample_sku_week_df: pd.DataFrame):
    builder = SupervisedDatasetBuilder(random_seed=42)
    splits = builder.split_by_sku(sample_sku_week_df, train_ratio=0.7, val_ratio=0.3, test_ratio=0.0)

    forecaster = LightGBMForecaster(n_estimators=30, random_seed=42)
    forecaster.fit(splits.df_train)

    predictor = ColdStartPredictor(forecaster)

    sku_attr = {
        "sku_id": "NEW_PRODUCT_999",
        "category": "Apparel",
        "subcategory": "Apparel_Sub",
        "base_price": 59.99,
        "brand_tier": "Tier 1 National",
        "launch_date": "2025-11-03",
        "has_marketing_support": True,
    }

    result: SKUWeeklyForecast = predictor.predict_sku(sku_attr)

    assert result.sku_id == "NEW_PRODUCT_999"
    assert len(result.weekly_forecast) == 8
    assert result.cumulative_8w_forecast == pytest.approx(sum(result.weekly_forecast), rel=1e-4)
    assert all(p >= 0.0 for p in result.weekly_forecast)


def test_model_artifact_save_and_load(sample_sku_week_df: pd.DataFrame, tmp_path: Path):
    builder = SupervisedDatasetBuilder(random_seed=42)
    splits = builder.split_by_sku(sample_sku_week_df, train_ratio=0.7, val_ratio=0.3, test_ratio=0.0)

    forecaster = LightGBMForecaster(n_estimators=30, random_seed=42)
    forecaster.fit(splits.df_train)

    artifact_dir = tmp_path / "model_artifact"
    forecaster.save_artifact(artifact_dir)

    # Load from disk
    loaded_predictor = ColdStartPredictor.from_artifact(artifact_dir)

    sku_attr = {
        "sku_id": "TEST_LOAD_SKU",
        "category": "Footwear",
        "base_price": 89.99,
        "launch_date": "2025-12-01",
    }

    original_predictor = ColdStartPredictor(forecaster)
    orig_res = original_predictor.predict_sku(sku_attr)
    loaded_res = loaded_predictor.predict_sku(sku_attr)

    assert orig_res.weekly_forecast == loaded_res.weekly_forecast
    assert orig_res.cumulative_8w_forecast == loaded_res.cumulative_8w_forecast


def test_unseen_category_and_missing_values_inference(sample_sku_week_df: pd.DataFrame):
    builder = SupervisedDatasetBuilder(random_seed=42)
    splits = builder.split_by_sku(sample_sku_week_df, train_ratio=0.7, val_ratio=0.3, test_ratio=0.0)

    forecaster = LightGBMForecaster(n_estimators=30, random_seed=42)
    forecaster.fit(splits.df_train)
    predictor = ColdStartPredictor(forecaster)

    # Completely novel / unobserved category, unknown brand, missing colour
    novel_sku = {
        "sku_id": "NOVEL_01",
        "category": "ExtraterrestrialGear",  # Completely unseen
        "subcategory": "LaserBoots",          # Completely unseen
        "colour": None,                      # Missing
        "material": None,                    # Missing
        "brand": "AlienTech",                # Unseen
        "base_price": 199.99,
        "launch_date": "2026-03-01",
    }

    result = predictor.predict_sku(novel_sku)
    assert len(result.weekly_forecast) == 8
    assert all(p >= 0.0 for p in result.weekly_forecast)
    assert not any(np.isnan(result.weekly_forecast))
