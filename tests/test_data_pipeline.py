"""Comprehensive unit tests for Phase 2 data pipeline and data quality auditing."""

from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.data.pipeline import DataPipeline
from src.data.quality import DataQualityAuditor, DataQualityConfig
from src.data.schema import ObservationStatus, PriceBand


@pytest.fixture
def sample_pipeline(tmp_path: Path) -> DataPipeline:
    """Creates a DataPipeline instance with temporary directories."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    processed = tmp_path / "processed"
    raw.mkdir()
    return DataPipeline(raw_dir=raw, interim_dir=interim, processed_dir=processed)


def test_malformed_rows_and_negative_prices(sample_pipeline: DataPipeline):
    # Malformed sales: negative sales and non-date strings
    df_sales = pd.DataFrame({
        "sku_id": ["SKU_1", "SKU_1", "SKU_2"],
        "store_id": ["S1", "S1", "S1"],
        "week_start_date": ["2024-01-08", "2024-01-08", "2024-01-15"],  # First two are duplicates
        "units_sold": [25.0, -10.0, "corrupted_val"],
    })
    clean_sales = sample_pipeline._normalize_sales(df_sales)

    # First duplicate kept, negative clipped to 0, corrupted coerced to 0
    assert len(clean_sales) == 2
    assert (clean_sales["units_sold"] >= 0).all()
    assert clean_sales.loc[clean_sales["sku_id"] == "SKU_2", "units_sold"].values[0] == 0.0


def test_missing_attributes_imputation(sample_pipeline: DataPipeline):
    df_attr = pd.DataFrame({
        "sku_id": ["SKU_100"],
        "category": ["Apparel"],
        "subcategory": [None],
        "colour": [None],
        "material": [None],
        "base_price": [None],
        "brand": [None],
        "launch_date": ["2024-05-06"],
    })

    # Fit pipeline encoders with known category
    sample_pipeline.known_categories = {"Apparel"}
    sample_pipeline.training_median_price = 39.99

    norm_attr = sample_pipeline._normalize_attributes(df_attr, is_target_eval=False)
    features = sample_pipeline._transform_attributes(norm_attr)

    assert features.iloc[0]["subcategory"] == "missing"
    assert features.iloc[0]["colour"] == "missing"
    assert features.iloc[0]["material"] == "missing"
    assert features.iloc[0]["base_price"] == 39.99
    assert features.iloc[0]["price_band"] == PriceBand.MID_RANGE.value


def test_duplicate_detection_and_deduplication(sample_pipeline: DataPipeline):
    df_stores = pd.DataFrame({
        "store_id": ["S1", "S1", "S2"],
        "cluster_id": ["C1", "C1", "C2"],
        "region": ["North", "North", "South"],
    })
    clean_stores = sample_pipeline._normalize_stores(df_stores)
    assert len(clean_stores) == 2
    assert clean_stores["store_id"].tolist() == ["S1", "S2"]


def test_unseen_categories_handling(sample_pipeline: DataPipeline):
    # Training knows only Apparel and Footwear
    sample_pipeline.known_categories = {"Apparel", "Footwear"}
    sample_pipeline.known_brands = {"BrandAlpha"}

    df_test_attr = pd.DataFrame({
        "sku_id": ["SKU_NEW_1"],
        "category": ["NoveltyCategory"],  # Unseen
        "subcategory": ["RareSubCat"],     # Unseen
        "colour": ["NeonPink"],            # Unseen
        "material": ["CarbonFiber"],       # Unseen
        "brand": ["UnknownBrand"],         # Unseen
        "base_price": [120.0],
        "launch_date": ["2025-10-06"],
    })

    norm_test = sample_pipeline._normalize_attributes(df_test_attr, is_target_eval=True)
    transformed = sample_pipeline._transform_attributes(norm_test)

    assert transformed.iloc[0]["category"] == "_UNKNOWN_"
    assert transformed.iloc[0]["subcategory"] == "_UNKNOWN_"
    assert transformed.iloc[0]["colour"] == "_UNKNOWN_"
    assert transformed.iloc[0]["material"] == "_UNKNOWN_"
    assert transformed.iloc[0]["brand"] == "_UNKNOWN_"
    assert transformed.iloc[0]["price_band"] == PriceBand.PREMIUM.value


def test_launch_age_alignment(sample_pipeline: DataPipeline):
    # SKU launched on 2024-01-01 (Monday)
    df_mature = pd.DataFrame({
        "sku_id": ["SKU_A"],
        "category": ["Apparel"],
        "subcategory": ["Jackets"],
        "colour": ["Black"],
        "material": ["Cotton"],
        "brand": ["Apex"],
        "brand_tier": ["Tier 1 National"],
        "base_price": [50.0],
        "launch_date": ["2024-01-01"],
        "has_marketing_support": [True],
    })

    # Sales observations across 10 weeks
    sales_rows = []
    for w in range(10):
        sale_date = (date(2024, 1, 1) + pd.Timedelta(days=w * 7)).strftime("%Y-%m-%d")
        sales_rows.append({
            "sku_id": "SKU_A",
            "store_id": "STORE_1",
            "week_start_date": sale_date,
            "units_sold": 10.0 + w,
        })
    df_sales = pd.DataFrame(sales_rows)

    df_stores = pd.DataFrame([{"store_id": "STORE_1", "cluster_id": "CLUSTER_1"}])
    df_cal = pd.DataFrame([
        {"week_start_date": r["week_start_date"], "is_holiday_week": 0, "holiday_name": "None"}
        for r in sales_rows
    ])

    features = sample_pipeline.build_training_features(df_sales, df_mature, df_stores, df_cal)

    # Must be filtered strictly to weeks 1 through 8 (10 weeks originally)
    assert len(features) == 8
    assert features["launch_week_age"].tolist() == [1, 2, 3, 4, 5, 6, 7, 8]


def test_marketing_flag_business_rule(sample_pipeline: DataPipeline):
    # Rule: has_marketing_support=True -> flag=1 for W1..W4, flag=0 for W5..W8
    for w in [1, 2, 3, 4]:
        assert sample_pipeline.apply_marketing_business_rule(has_marketing_support=True, launch_week_age=w) == 1
    for w in [5, 6, 7, 8]:
        assert sample_pipeline.apply_marketing_business_rule(has_marketing_support=True, launch_week_age=w) == 0

    # Without marketing support -> 0 everywhere
    for w in range(1, 9):
        assert sample_pipeline.apply_marketing_business_rule(has_marketing_support=False, launch_week_age=w) == 0


def test_strict_data_leakage_fencing(sample_pipeline: DataPipeline):
    # Mature SKU
    df_mature = pd.DataFrame([{
        "sku_id": "SKU_MATURE_1",
        "category": "Apparel",
        "subcategory": "Jeans",
        "colour": "Blue",
        "material": "Denim",
        "brand": "Core",
        "brand_tier": "Tier 2 Regional",
        "base_price": 40.0,
        "launch_date": "2024-01-01",
        "has_marketing_support": True,
    }])
    df_sales = pd.DataFrame([{
        "sku_id": "SKU_MATURE_1",
        "store_id": "S1",
        "week_start_date": "2024-01-01",
        "units_sold": 50.0,
    }])

    # Target Eval SKU
    df_new = pd.DataFrame([{
        "sku_id": "SKU_EVAL_999",
        "category": "Apparel",
        "subcategory": "Jeans",
        "colour": "Blue",
        "material": "Denim",
        "brand": "Core",
        "brand_tier": "Tier 2 Regional",
        "base_price": 45.0,
        "launch_date": "2025-11-03",
        "has_marketing_support": False,
    }])

    df_stores = pd.DataFrame([{"store_id": "S1", "cluster_id": "C1"}])
    df_cal = pd.DataFrame([
        {"week_start_date": "2024-01-01", "is_holiday_week": 0, "holiday_name": "None"},
        {"week_start_date": "2025-11-03", "is_holiday_week": 0, "holiday_name": "None"},
    ])

    train_df = sample_pipeline.build_training_features(df_sales, df_mature, df_stores, df_cal)
    inf_df = sample_pipeline.build_inference_features(df_new, df_stores, df_cal)

    # 1. Zero SKU overlap
    assert set(train_df["sku_id"]).isdisjoint(set(inf_df["sku_id"]))

    # 2. Target units_sold is strictly null in inference features
    assert inf_df["units_sold"].isnull().all()

    # 3. Quality audit flags zero leakage
    auditor = DataQualityAuditor()
    report = auditor.audit_processed_features(train_df, inf_df)
    assert report.leakage_check_passed is True


def test_stockout_non_invention(sample_pipeline: DataPipeline):
    # When days_in_stock is not present, pipeline does not invent it
    df_sales = pd.DataFrame({
        "sku_id": ["SKU_1", "SKU_2"],
        "store_id": ["S1", "S1"],
        "week_start_date": ["2024-01-08", "2024-01-08"],
        "units_sold": [0.0, 15.0],
    })
    clean_sales = sample_pipeline._normalize_sales(df_sales)

    # days_in_stock is preserved as NaN (not invented)
    assert clean_sales["days_in_stock"].isnull().all()
