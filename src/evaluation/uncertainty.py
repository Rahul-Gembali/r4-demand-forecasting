"""Uncertainty Estimation and Conformal Prediction Engine for Cold-Start Demand.

Implements Split Conformal Prediction, Conformalized Quantile Calibration,
weekly and cumulative 8-week prediction intervals, empirical coverage metrics,
Winkler score, and serialization for production inference.
"""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.logging import logger
from src.evaluation.metrics import (
    pinball_loss,
)


def empirical_coverage(y_true: Any, lower_bound: Any, upper_bound: Any) -> float:
    """Calculates empirical coverage percentage in [0.0, 1.0]."""
    yt = np.asarray(y_true, dtype=np.float64).flatten()
    lb = np.asarray(lower_bound, dtype=np.float64).flatten()
    ub = np.asarray(upper_bound, dtype=np.float64).flatten()

    if not (len(yt) == len(lb) == len(ub)):
        raise ValueError("Array lengths must match.")

    covered = (yt >= lb) & (yt <= ub)
    return float(np.mean(covered))


def mean_interval_width(lower_bound: Any, upper_bound: Any) -> float:
    """Calculates average prediction interval width (upper - lower)."""
    lb = np.asarray(lower_bound, dtype=np.float64).flatten()
    ub = np.asarray(upper_bound, dtype=np.float64).flatten()

    if len(lb) != len(ub):
        raise ValueError("Array lengths must match.")

    diffs = ub - lb
    if np.any(diffs < -1e-6):
        raise ValueError("Found instances where lower_bound exceeds upper_bound.")

    return float(np.mean(np.maximum(0.0, diffs)))


def winkler_score(y_true: Any, lower_bound: Any, upper_bound: Any, alpha: float = 0.10) -> float:
    """Calculates Winkler Score (Interval Score) at significance level alpha (Gneiting & Raftery 2007).

    For nominal coverage (1 - alpha):
    Score = (U - L) + (2/alpha)*(L - y)*I(y < L) + (2/alpha)*(y - U)*I(y > U)
    Lower score indicates sharper, better-calibrated intervals.
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"Significance level alpha must be in (0, 1), got {alpha}")

    yt = np.asarray(y_true, dtype=np.float64).flatten()
    lb = np.asarray(lower_bound, dtype=np.float64).flatten()
    ub = np.asarray(upper_bound, dtype=np.float64).flatten()

    if not (len(yt) == len(lb) == len(ub)):
        raise ValueError("Array lengths must match.")

    width = ub - lb
    penalty_low = np.where(yt < lb, (2.0 / alpha) * (lb - yt), 0.0)
    penalty_high = np.where(yt > ub, (2.0 / alpha) * (yt - ub), 0.0)

    score = width + penalty_low + penalty_high
    return float(np.mean(score))


@dataclass
class IntervalMetrics:
    """Evaluation metrics for a prediction interval."""
    confidence_level: float
    target_coverage: float
    empirical_coverage: float
    mean_width: float
    winkler_score: float
    pinball_lower: float
    pinball_upper: float


class ConformalIntervalCalibrator:
    """Split Conformal Prediction Engine for Enterprise Retail Cold-Start Demand.

    Calibrates on held-out validation cohorts (zero leakage) to produce finite-sample
    distribution-free valid prediction intervals for weekly and cumulative 8-week demand.
    """

    def __init__(self, min_spread_epsilon: float = 5.0, spread_power: float = 0.85):
        self.min_spread_epsilon = min_spread_epsilon
        self.spread_power = spread_power
        self.is_calibrated = False

        # Cutoffs keyed by alpha: e.g. 0.20 -> 80% coverage, 0.10 -> 90% coverage
        self.weekly_cutoffs: dict[float, float] = {}
        self.cumulative_cutoffs: dict[float, float] = {}
        self.calibration_metadata: dict[str, Any] = {}

    def _estimate_spread(self, y_pred: np.ndarray) -> np.ndarray:
        """Estimates heteroscedastic scale factor proportional to demand level."""
        clean_pred = np.maximum(0.0, y_pred)
        return np.maximum(self.min_spread_epsilon, clean_pred ** self.spread_power)

    def calibrate(
        self,
        df_val_panel: pd.DataFrame,
        val_preds: np.ndarray,
        confidence_levels: list[float] | None = None,
    ) -> "ConformalIntervalCalibrator":
        """Calibrates non-conformity multipliers using validation SKU observations.

        Parameters
        ----------
        df_val_panel : pd.DataFrame
            Must contain 'sku_id', 'launch_week_age', and 'units_sold'.
        val_preds : np.ndarray
            Predicted point sales for the corresponding rows in df_val_panel.
        confidence_levels : list[float]
            Nominal coverage targets, e.g. [0.80, 0.90].
        """
        if confidence_levels is None:
            confidence_levels = [0.80, 0.90]

        logger.info("Calibrating ConformalIntervalCalibrator on %d validation records...", len(df_val_panel))

        df_cal = df_val_panel.copy()
        df_cal["pred"] = np.maximum(0.0, val_preds)
        df_cal["actual"] = np.maximum(0.0, df_cal["units_sold"].to_numpy())

        # 1. Weekly Non-Conformity Scores
        sigma_weekly = self._estimate_spread(df_cal["pred"].to_numpy())
        weekly_scores = np.abs(df_cal["actual"] - df_cal["pred"]) / sigma_weekly
        n_weekly = len(weekly_scores)

        # 2. Cumulative 8-Week Non-Conformity Scores (Aggregated strictly by SKU)
        sku_cum = df_cal.groupby("sku_id").agg({
            "actual": "sum",
            "pred": "sum",
        }).reset_index()
        sigma_cum = self._estimate_spread(sku_cum["pred"].to_numpy())
        cumulative_scores = np.abs(sku_cum["actual"] - sku_cum["pred"]) / sigma_cum
        n_cum = len(cumulative_scores)

        # 3. Compute Conformal Cutoffs for each required confidence level
        for conf in confidence_levels:
            alpha = round(1.0 - conf, 4)
            # Finite-sample conformal quantile: ceil((n + 1) * (1 - alpha)) / n
            k_weekly = min(1.0, math.ceil((n_weekly + 1) * (1.0 - alpha)) / n_weekly)
            q_w = float(np.quantile(weekly_scores, k_weekly))
            self.weekly_cutoffs[conf] = round(q_w, 6)

            k_cum = min(1.0, math.ceil((n_cum + 1) * (1.0 - alpha)) / n_cum)
            q_c = float(np.quantile(cumulative_scores, k_cum))
            self.cumulative_cutoffs[conf] = round(q_c, 6)

            logger.info(
                "Level %.2f (alpha=%.2f): Weekly Cutoff=%.4f (N=%d), Cumulative Cutoff=%.4f (N=%d)",
                conf, alpha, q_w, n_weekly, q_c, n_cum
            )

        self.calibration_metadata = {
            "calibrated_at": datetime.now(UTC).isoformat(),
            "n_weekly_calibration_points": n_weekly,
            "n_skus_calibration": n_cum,
            "min_spread_epsilon": self.min_spread_epsilon,
            "spread_power": self.spread_power,
            "confidence_levels": confidence_levels,
            "weekly_cutoffs": self.weekly_cutoffs,
            "cumulative_cutoffs": self.cumulative_cutoffs,
        }
        self.is_calibrated = True
        return self

    def predict_weekly_intervals(
        self,
        y_pred: np.ndarray,
        confidence_level: float = 0.90,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generates lower and upper prediction bounds for weekly forecasts."""
        if not self.is_calibrated:
            raise RuntimeError("Calibrator is not calibrated. Call calibrate() first.")

        if confidence_level not in self.weekly_cutoffs:
            available = list(self.weekly_cutoffs.keys())
            raise ValueError(f"Confidence level {confidence_level} not calibrated. Available: {available}")

        yp = np.maximum(0.0, np.asarray(y_pred, dtype=np.float64))
        q_w = self.weekly_cutoffs[confidence_level]
        sigma = self._estimate_spread(yp)

        half_width = q_w * sigma
        lower_bound = np.maximum(0.0, np.round(yp - half_width, 2))
        upper_bound = np.maximum(lower_bound, np.round(yp + half_width, 2))

        return lower_bound, upper_bound

    def predict_cumulative_intervals(
        self,
        y_pred_cumul: np.ndarray,
        confidence_level: float = 0.90,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generates dedicated lower and upper prediction bounds for cumulative 8-week demand."""
        if not self.is_calibrated:
            raise RuntimeError("Calibrator is not calibrated. Call calibrate() first.")

        if confidence_level not in self.cumulative_cutoffs:
            available = list(self.cumulative_cutoffs.keys())
            raise ValueError(f"Confidence level {confidence_level} not calibrated. Available: {available}")

        yp = np.maximum(0.0, np.asarray(y_pred_cumul, dtype=np.float64))
        q_c = self.cumulative_cutoffs[confidence_level]
        sigma = self._estimate_spread(yp)

        half_width = q_c * sigma
        lower_bound = np.maximum(0.0, np.round(yp - half_width, 2))
        upper_bound = np.maximum(lower_bound, np.round(yp + half_width, 2))

        return lower_bound, upper_bound

    def evaluate(
        self,
        y_true: Any,
        lower_bound: Any,
        upper_bound: Any,
        confidence_level: float,
    ) -> IntervalMetrics:
        """Evaluates empirical coverage, width, Winkler score, and pinball loss."""
        alpha = round(1.0 - confidence_level, 4)
        cov = empirical_coverage(y_true, lower_bound, upper_bound)
        width = mean_interval_width(lower_bound, upper_bound)
        w_score = winkler_score(y_true, lower_bound, upper_bound, alpha=alpha)

        p_low = pinball_loss(y_true, lower_bound, tau=alpha / 2.0)
        p_high = pinball_loss(y_true, upper_bound, tau=1.0 - (alpha / 2.0))

        return IntervalMetrics(
            confidence_level=confidence_level,
            target_coverage=confidence_level,
            empirical_coverage=round(cov, 4),
            mean_width=round(width, 2),
            winkler_score=round(w_score, 2),
            pinball_lower=round(p_low, 2),
            pinball_upper=round(p_high, 2),
        )

    def save(self, filepath: Path) -> None:
        """Serializes calibration parameters to JSON."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.calibration_metadata, f, indent=2)
        logger.info("Saved ConformalIntervalCalibrator metadata to: %s", filepath)

    @classmethod
    def load(cls, filepath: Path) -> "ConformalIntervalCalibrator":
        """Loads calibrator from serialized JSON metadata."""
        with open(filepath, encoding="utf-8") as f:
            meta = json.load(f)

        instance = cls(
            min_spread_epsilon=meta.get("min_spread_epsilon", 5.0),
            spread_power=meta.get("spread_power", 0.85),
        )
        instance.weekly_cutoffs = {float(k): float(v) for k, v in meta["weekly_cutoffs"].items()}
        instance.cumulative_cutoffs = {float(k): float(v) for k, v in meta["cumulative_cutoffs"].items()}
        instance.calibration_metadata = meta
        instance.is_calibrated = True
        return instance
