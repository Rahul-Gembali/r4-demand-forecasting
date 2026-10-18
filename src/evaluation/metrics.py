"""Evaluation metrics for Cold-Start Demand Forecasting.

Implements WAPE, RMSE, MAE, Forecast Bias, and Pinball Loss.
"""

from typing import Any
import numpy as np


def ensure_numpy_arrays(
    y_true: Any, y_pred: Any
) -> tuple[np.ndarray, np.ndarray]:
    """Validates and converts inputs to flat float numpy arrays."""
    yt = np.asarray(y_true, dtype=np.float64).flatten()
    yp = np.asarray(y_pred, dtype=np.float64).flatten()

    if yt.shape != yp.shape:
        raise ValueError(f"Shape mismatch: y_true {yt.shape} vs y_pred {yp.shape}")

    if np.any(np.isnan(yt)) or np.any(np.isnan(yp)):
        raise ValueError("Inputs contain NaN values")

    if np.any(np.isinf(yt)) or np.any(np.isinf(yp)):
        raise ValueError("Inputs contain infinite values")

    return yt, yp


def wape(y_true: Any, y_pred: Any) -> float:
    """Calculates Weighted Absolute Percentage Error (WAPE).

    WAPE = sum(|y_true - y_pred|) / sum(y_true)
    """
    yt, yp = ensure_numpy_arrays(y_true, y_pred)
    total_actual = float(np.sum(yt))
    total_abs_error = float(np.sum(np.abs(yt - yp)))

    if total_actual == 0.0:
        return 0.0 if total_abs_error == 0.0 else float("inf")

    return total_abs_error / total_actual


def rmse(y_true: Any, y_pred: Any) -> float:
    """Calculates Root Mean Squared Error (RMSE)."""
    yt, yp = ensure_numpy_arrays(y_true, y_pred)
    if len(yt) == 0:
        return 0.0
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def mae(y_true: Any, y_pred: Any) -> float:
    """Calculates Mean Absolute Error (MAE)."""
    yt, yp = ensure_numpy_arrays(y_true, y_pred)
    if len(yt) == 0:
        return 0.0
    return float(np.mean(np.abs(yt - yp)))


def forecast_bias_pct(y_true: Any, y_pred: Any) -> float:
    """Calculates aggregate Forecast Bias Percentage.

    Bias % = sum(y_pred - y_true) / sum(y_true) * 100%
    """
    yt, yp = ensure_numpy_arrays(y_true, y_pred)
    total_actual = float(np.sum(yt))
    total_diff = float(np.sum(yp - yt))

    if total_actual == 0.0:
        return 0.0 if total_diff == 0.0 else float("inf")

    return (total_diff / total_actual) * 100.0


def pinball_loss(y_true: Any, y_pred: Any, tau: float = 0.5) -> float:
    """Calculates Pinball Loss for quantile regression at level tau (0 < tau < 1)."""
    if not (0.0 < tau < 1.0):
        raise ValueError(f"Quantile tau must be in (0, 1), got {tau}")

    yt, yp = ensure_numpy_arrays(y_true, y_pred)
    diff = yt - yp
    loss = np.maximum(tau * diff, (tau - 1.0) * diff)
    return float(np.mean(loss))


def calculate_metrics_summary(y_true: Any, y_pred: Any) -> dict[str, float]:
    """Returns a dictionary summarizing all primary forecasting metrics."""
    return {
        "wape": wape(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "mae": mae(y_true, y_pred),
        "bias_pct": forecast_bias_pct(y_true, y_pred),
        "pinball_p50": pinball_loss(y_true, y_pred, tau=0.5),
        "pinball_p90": pinball_loss(y_true, y_pred, tau=0.9),
    }
