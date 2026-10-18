"""Unit tests for Phase 5 Uncertainty Estimation and Official Evaluation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.evaluation.official_evaluator import OfficialEvaluationReport, OfficialEvaluator
from src.evaluation.uncertainty import (
    ConformalIntervalCalibrator,
    empirical_coverage,
    mean_interval_width,
    winkler_score,
)


def test_empirical_coverage_and_width_calculation():
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    lb = np.array([5.0, 15.0, 35.0, 30.0])  # 30.0 is missed (35.0 > 30.0)
    ub = np.array([15.0, 25.0, 45.0, 50.0])

    cov = empirical_coverage(y_true, lb, ub)
    assert cov == 0.75

    width = mean_interval_width(lb, ub)
    assert width == pytest.approx(12.5)

    # Invalid input checks
    with pytest.raises(ValueError, match="Array lengths must match"):
        empirical_coverage(y_true, lb[:3], ub)

    with pytest.raises(ValueError, match="lower_bound exceeds upper_bound"):
        mean_interval_width([15.0], [10.0])


def test_winkler_score_properties():
    # 90% confidence -> alpha = 0.10, penalty multiplier 2/alpha = 20.0
    # Case 1: Observation inside interval
    s1 = winkler_score([25.0], [20.0], [30.0], alpha=0.10)
    assert s1 == pytest.approx(10.0)  # width only: 30 - 20 = 10

    # Case 2: Observation below lower bound by 2 units
    s2 = winkler_score([18.0], [20.0], [30.0], alpha=0.10)
    # width (10) + 20 * (20 - 18) = 10 + 40 = 50
    assert s2 == pytest.approx(50.0)

    # Case 3: Observation above upper bound by 3 units
    s3 = winkler_score([33.0], [20.0], [30.0], alpha=0.10)
    # width (10) + 20 * (33 - 30) = 10 + 60 = 70
    assert s3 == pytest.approx(70.0)


def test_conformal_calibrator_bounds_and_monotonicity():
    # Synthetic calibration data
    cal_records = []
    for i in range(1, 21):
        for w in range(1, 9):
            base = 100.0 + i * 2.0
            cal_records.append({
                "sku_id": f"CAL_SKU_{i:02d}",
                "launch_week_age": w,
                "units_sold": base + np.random.normal(0.0, 10.0),
            })
    df_cal = pd.DataFrame(cal_records)
    preds = np.full(len(df_cal), 100.0)

    calibrator = ConformalIntervalCalibrator()
    calibrator.calibrate(df_cal, preds, confidence_levels=[0.80, 0.90])

    assert calibrator.is_calibrated
    assert 0.80 in calibrator.weekly_cutoffs
    assert 0.90 in calibrator.weekly_cutoffs
    assert calibrator.weekly_cutoffs[0.90] >= calibrator.weekly_cutoffs[0.80]

    test_preds = np.array([50.0, 120.0, 200.0])
    l80, u80 = calibrator.predict_weekly_intervals(test_preds, confidence_level=0.80)
    l90, u90 = calibrator.predict_weekly_intervals(test_preds, confidence_level=0.90)

    # 1. Non-negativity
    assert (l80 >= 0.0).all()
    assert (l90 >= 0.0).all()

    # 2. Lower <= Upper
    assert (l80 <= u80).all()
    assert (l90 <= u90).all()

    # 3. 90% interval contains 80% interval (wider bounds)
    assert (l90 <= l80).all()
    assert (u90 >= u80).all()


def test_cumulative_interval_is_tighter_than_naive_sum():
    cal_records = []
    for i in range(1, 26):
        for w in range(1, 9):
            cal_records.append({
                "sku_id": f"SKU_{i:02d}",
                "launch_week_age": w,
                "units_sold": 50.0 + np.random.normal(0.0, 8.0),
            })
    df_cal = pd.DataFrame(cal_records)
    preds = np.full(len(df_cal), 50.0)

    calibrator = ConformalIntervalCalibrator()
    calibrator.calibrate(df_cal, preds, confidence_levels=[0.90])

    sku_weekly_preds = np.full(8, 50.0)
    w_low, w_up = calibrator.predict_weekly_intervals(sku_weekly_preds, confidence_level=0.90)
    naive_cumul_width = sum(w_up - w_low)

    cumul_pred = np.array([400.0])
    c_low, c_up = calibrator.predict_cumulative_intervals(cumul_pred, confidence_level=0.90)
    dedicated_cumul_width = float((c_up - c_low)[0])

    # Mathematical property: dedicated calibration is substantially sharper than naive summing
    assert dedicated_cumul_width < naive_cumul_width
    assert dedicated_cumul_width < 0.75 * naive_cumul_width


def test_official_evaluator_validation_rules():
    evaluator = OfficialEvaluator(target_sku_count=2, strict_row_count=True)

    # Valid dataframe
    valid_df = pd.DataFrame({
        "sku_id": ["SKU_1"] * 8 + ["SKU_2"] * 8,
        "horizon_week": list(range(1, 9)) * 2,
        "predicted_sales": [10.0] * 16,
    })
    evaluator.validate_submission_format(valid_df)

    # 1. Missing columns
    with pytest.raises(ValueError, match="missing required columns"):
        evaluator.validate_submission_format(valid_df.drop(columns=["predicted_sales"]))

    # 2. Negative predictions
    neg_df = valid_df.copy()
    neg_df.loc[0, "predicted_sales"] = -5.0
    with pytest.raises(ValueError, match="negative predicted values"):
        evaluator.validate_submission_format(neg_df)

    # 3. Null values
    null_df = valid_df.copy()
    null_df.loc[0, "predicted_sales"] = None
    with pytest.raises(ValueError, match="null values"):
        evaluator.validate_submission_format(null_df)

    # 4. Duplicate keys
    dup_df = pd.concat([valid_df, valid_df.iloc[:1]])
    with pytest.raises(ValueError, match="Duplicate"):
        evaluator.validate_submission_format(dup_df)

    # 5. Invalid horizon weeks
    bad_week_df = valid_df.copy()
    bad_week_df.loc[0, "horizon_week"] = 9
    with pytest.raises(ValueError, match="strictly contain values 1 to 8"):
        evaluator.validate_submission_format(bad_week_df)


def test_official_evaluator_evaluation_and_zero_denominator():
    evaluator = OfficialEvaluator()

    preds = pd.DataFrame({
        "sku_id": ["SKU_A", "SKU_A"],
        "horizon_week": [1, 2],
        "predicted_sales": [100.0, 50.0],
    })
    truth = pd.DataFrame({
        "sku_id": ["SKU_A", "SKU_A"],
        "horizon_week": [1, 2],
        "actual_sales": [120.0, 40.0],
    })

    report: OfficialEvaluationReport = evaluator.evaluate(preds, truth)
    assert report.total_skus == 1
    assert report.total_horizon_points == 2
    # WAPE = (|120-100| + |40-50|) / (120+40) = 30 / 160 = 0.1875
    assert report.overall_wape == pytest.approx(0.1875, rel=1e-4)
    assert report.weekly_wape[1] == pytest.approx(20.0 / 120.0, rel=1e-4)
    assert report.weekly_wape[2] == pytest.approx(10.0 / 40.0, rel=1e-4)

    # Zero actuals handling
    zero_truth = pd.DataFrame({
        "sku_id": ["SKU_Z"],
        "horizon_week": [1],
        "actual_sales": [0.0],
    })
    zero_pred = pd.DataFrame({
        "sku_id": ["SKU_Z"],
        "horizon_week": [1],
        "predicted_sales": [0.0],
    })
    zero_report = evaluator.evaluate(zero_pred, zero_truth)
    assert zero_report.overall_wape == 0.0
    assert zero_report.overall_bias_pct == 0.0


def test_calibrator_serialization_roundtrip(tmp_path: Path):
    calibrator = ConformalIntervalCalibrator()
    calibrator.is_calibrated = True
    calibrator.weekly_cutoffs = {0.80: 0.75, 0.90: 1.10}
    calibrator.cumulative_cutoffs = {0.80: 0.35, 0.90: 0.55}
    calibrator.calibration_metadata = {
        "weekly_cutoffs": calibrator.weekly_cutoffs,
        "cumulative_cutoffs": calibrator.cumulative_cutoffs,
        "min_spread_epsilon": 5.0,
        "spread_power": 0.85,
    }

    save_path = tmp_path / "uncertainty_config.json"
    calibrator.save(save_path)

    loaded = ConformalIntervalCalibrator.load(save_path)
    assert loaded.is_calibrated
    assert loaded.weekly_cutoffs == calibrator.weekly_cutoffs
    assert loaded.cumulative_cutoffs == calibrator.cumulative_cutoffs

    preds = np.array([80.0, 150.0])
    l_orig, u_orig = calibrator.predict_weekly_intervals(preds, 0.90)
    l_load, u_load = loaded.predict_weekly_intervals(preds, 0.90)
    np.testing.assert_array_equal(l_orig, l_load)
    np.testing.assert_array_equal(u_orig, u_load)
