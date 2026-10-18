"""Unit tests for forecasting evaluation metrics and ColdStartEvaluator."""

import numpy as np
import pandas as pd
import pytest

from src.evaluation.evaluator import ColdStartEvaluator
from src.evaluation.metrics import (
    calculate_metrics_summary,
    forecast_bias_pct,
    mae,
    pinball_loss,
    rmse,
    wape,
)


def test_perfect_predictions():
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([10.0, 20.0, 30.0, 40.0])

    assert wape(y_true, y_pred) == 0.0
    assert rmse(y_true, y_pred) == 0.0
    assert mae(y_true, y_pred) == 0.0
    assert forecast_bias_pct(y_true, y_pred) == 0.0
    assert pinball_loss(y_true, y_pred, tau=0.5) == 0.0


def test_known_metric_values():
    y_true = np.array([100.0, 200.0, 300.0])
    y_pred = np.array([110.0, 190.0, 330.0])

    # sum abs diff = 10 + 10 + 30 = 50. Total actual = 600.
    expected_wape = 50.0 / 600.0
    expected_mae = 50.0 / 3.0
    expected_rmse = np.sqrt((100 + 100 + 900) / 3.0)
    expected_bias = (30.0 / 600.0) * 100.0

    assert pytest.approx(wape(y_true, y_pred), rel=1e-5) == expected_wape
    assert pytest.approx(mae(y_true, y_pred), rel=1e-5) == expected_mae
    assert pytest.approx(rmse(y_true, y_pred), rel=1e-5) == expected_rmse
    assert pytest.approx(forecast_bias_pct(y_true, y_pred), rel=1e-5) == expected_bias


def test_pinball_loss_asymmetry():
    y_true = np.array([100.0])
    # Under-prediction: y_true > y_pred (diff = 20)
    y_pred_under = np.array([80.0])
    # Over-prediction: y_true < y_pred (diff = -20)
    y_pred_over = np.array([120.0])

    # At tau = 0.9, under-prediction penalty is 0.9 * 20 = 18.0
    assert pinball_loss(y_true, y_pred_under, tau=0.9) == pytest.approx(18.0)
    # At tau = 0.9, over-prediction penalty is (0.9 - 1) * (-20) = 2.0
    assert pinball_loss(y_true, y_pred_over, tau=0.9) == pytest.approx(2.0)


def test_zero_actuals_handling():
    y_true = np.array([0.0, 0.0, 0.0])
    y_pred_zeros = np.array([0.0, 0.0, 0.0])
    y_pred_nonzero = np.array([5.0, 0.0, 0.0])

    assert wape(y_true, y_pred_zeros) == 0.0
    assert wape(y_true, y_pred_nonzero) == float("inf")
    assert forecast_bias_pct(y_true, y_pred_zeros) == 0.0
    assert forecast_bias_pct(y_true, y_pred_nonzero) == float("inf")


def test_invalid_input_shapes_and_nans():
    with pytest.raises(ValueError, match="Shape mismatch"):
        wape([1, 2], [1, 2, 3])

    with pytest.raises(ValueError, match="NaN"):
        rmse([1, np.nan], [1, 2])

    with pytest.raises(ValueError, match="infinite"):
        mae([1, np.inf], [1, 2])


def test_evaluator_submission_validation():
    evaluator = ColdStartEvaluator()

    # Missing column
    df_missing = pd.DataFrame({"sku_id": ["S1"], "horizon_week": [1]})
    with pytest.raises(ValueError, match="missing required columns"):
        evaluator.validate_predictions(df_missing)

    # Negative values
    df_neg = pd.DataFrame({"sku_id": ["S1"], "horizon_week": [1], "predicted_sales": [-10.0]})
    with pytest.raises(ValueError, match="negative predicted values"):
        evaluator.validate_predictions(df_neg)

    # Invalid horizon week
    df_invalid_w = pd.DataFrame({"sku_id": ["S1"], "horizon_week": [9], "predicted_sales": [10.0]})
    with pytest.raises(ValueError, match="between 1 and 8"):
        evaluator.validate_predictions(df_invalid_w)

    # Duplicates
    df_dups = pd.DataFrame({
        "sku_id": ["S1", "S1"],
        "horizon_week": [1, 1],
        "predicted_sales": [10.0, 20.0],
    })
    with pytest.raises(ValueError, match="duplicate"):
        evaluator.validate_predictions(df_dups)


def test_cold_start_evaluator_run():
    evaluator = ColdStartEvaluator()

    pred_records = []
    truth_records = []
    for sku in [f"SKU_{i:03d}" for i in range(1, 11)]:
        for w in range(1, 9):
            actual = 50.0 + w * 2.0
            pred = actual * 1.1  # 10% over-forecast
            truth_records.append({"sku_id": sku, "horizon_week": w, "actual_sales": actual})
            pred_records.append({"sku_id": sku, "horizon_week": w, "predicted_sales": pred})

    pred_df = pd.DataFrame(pred_records)
    truth_df = pd.DataFrame(truth_records)

    report = evaluator.evaluate(pred_df, truth_df)

    assert report.total_skus == 10
    assert report.total_eval_points == 80
    assert pytest.approx(report.overall_wape, rel=1e-4) == 0.10
    assert pytest.approx(report.overall_bias_pct, rel=1e-4) == 10.0
    assert len(report.weekly_wape) == 8
