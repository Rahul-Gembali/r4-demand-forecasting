"""Production Monitoring, Telemetry, Drift Detection, and Model Governance Engine.

Provides:
- Latency and throughput telemetry tracking (p50, p95, p99, error rates).
- Population Stability Index (PSI) and Total Variation Distance (TVD) data drift detection.
- Empirical prediction interval coverage monitoring.
- Strict Model Governance: Enforces that model promotion requires validated holdout WAPE
  and explicit human approval, strictly prohibiting automated promotion solely because
  drift is detected.
"""

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from src.core.logging import get_logger

logger = get_logger("core_monitoring")


class TelemetryTracker:
    """Thread-safe telemetry collector for API response times and error rates."""

    def __init__(self, max_history: int = 5000) -> None:
        self.max_history = max_history
        self._latencies: deque[float] = deque(maxlen=max_history)
        self._total_requests: int = 0
        self._error_counts: int = 0
        self._lock = threading.Lock()
        self._started_at = datetime.now(UTC)

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """Record an API request telemetry event."""
        with self._lock:
            self._total_requests += 1
            if status_code >= 400:
                self._error_counts += 1
            self._latencies.append(duration_ms)

    def get_summary(self) -> dict[str, Any]:
        """Compute latency percentiles and error metrics."""
        with self._lock:
            n = len(self._latencies)
            if n == 0:
                return {
                    "total_requests": self._total_requests,
                    "error_count": self._error_counts,
                    "error_rate_pct": 0.0,
                    "active_samples": 0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "max_ms": 0.0,
                    "avg_ms": 0.0,
                    "uptime_seconds": (datetime.now(UTC) - self._started_at).total_seconds(),
                }

            sorted_lat = sorted(self._latencies)
            p50 = float(np.percentile(sorted_lat, 50))
            p95 = float(np.percentile(sorted_lat, 95))
            p99 = float(np.percentile(sorted_lat, 99))
            avg = float(np.mean(sorted_lat))
            max_v = float(sorted_lat[-1])
            err_rate = (self._error_counts / self._total_requests * 100) if self._total_requests > 0 else 0.0

            return {
                "total_requests": self._total_requests,
                "error_count": self._error_counts,
                "error_rate_pct": round(err_rate, 2),
                "active_samples": n,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "max_ms": round(max_v, 2),
                "avg_ms": round(avg, 2),
                "uptime_seconds": round((datetime.now(UTC) - self._started_at).total_seconds(), 1),
            }


class DataDriftDetector:
    """Detects statistical feature drift between baseline training and inference datasets."""

    @staticmethod
    def calculate_psi(
        expected: np.ndarray,
        actual: np.ndarray,
        num_buckets: int = 10,
        epsilon: float = 1e-4,
    ) -> float:
        """Compute Population Stability Index (PSI) between baseline and production continuous feature."""
        clean_exp = expected[~np.isnan(expected)]
        clean_act = actual[~np.isnan(actual)]

        if len(clean_exp) < 10 or len(clean_act) < 10:
            return 0.0

        # Create quantile bins from expected distribution
        percentiles = np.linspace(0, 100, num_buckets + 1)
        bins = np.percentile(clean_exp, percentiles)
        bins = np.unique(bins)
        if len(bins) < 2:
            return 0.0

        bins[0] = -np.inf
        bins[-1] = np.inf

        exp_counts, _ = np.histogram(clean_exp, bins=bins)
        act_counts, _ = np.histogram(clean_act, bins=bins)

        exp_pct = np.maximum(exp_counts / len(clean_exp), epsilon)
        act_pct = np.maximum(act_counts / len(clean_act), epsilon)

        # Normalize
        exp_pct = exp_pct / np.sum(exp_pct)
        act_pct = act_pct / np.sum(act_pct)

        psi_val = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
        return float(max(0.0, psi_val))

    @staticmethod
    def calculate_category_tvd(expected: pd.Series, actual: pd.Series) -> float:
        """Compute Total Variation Distance (TVD) for categorical distribution shift."""
        exp_dist = expected.value_counts(normalize=True)
        act_dist = actual.value_counts(normalize=True)
        all_cats = set(exp_dist.index).union(set(act_dist.index))

        tvd = 0.5 * sum(abs(exp_dist.get(c, 0.0) - act_dist.get(c, 0.0)) for c in all_cats)
        return float(tvd)

    def assess_feature_drift(
        self,
        baseline_df: pd.DataFrame,
        current_df: pd.DataFrame,
        continuous_cols: list[str] | None = None,
        categorical_cols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate multi-feature drift against standard monitoring thresholds."""
        continuous_cols = continuous_cols or ["base_price"]
        categorical_cols = categorical_cols or ["category", "brand_tier"]

        drift_results: dict[str, Any] = {}
        any_significant_drift = False

        # Continuous features (PSI)
        for col in continuous_cols:
            if col in baseline_df.columns and col in current_df.columns:
                psi = self.calculate_psi(
                    baseline_df[col].to_numpy(dtype=float),
                    current_df[col].to_numpy(dtype=float),
                )
                severity = "NONE"
                if psi > 0.25:
                    severity = "SIGNIFICANT"
                    any_significant_drift = True
                elif psi > 0.10:
                    severity = "MODERATE"

                drift_results[col] = {
                    "metric": "PSI",
                    "score": round(psi, 4),
                    "severity": severity,
                }

        # Categorical features (TVD)
        for col in categorical_cols:
            if col in baseline_df.columns and col in current_df.columns:
                tvd = self.calculate_category_tvd(baseline_df[col], current_df[col])
                severity = "NONE"
                if tvd > 0.20:
                    severity = "SIGNIFICANT"
                    any_significant_drift = True
                elif tvd > 0.10:
                    severity = "MODERATE"

                drift_results[col] = {
                    "metric": "TVD",
                    "score": round(tvd, 4),
                    "severity": severity,
                }

        return {
            "drift_detected": any_significant_drift,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "features": drift_results,
        }


class UncertaintyCoverageMonitor:
    """Monitors holdout prediction interval coverage and alerts on interval degradation."""

    @staticmethod
    def evaluate_coverage(
        y_true: np.ndarray,
        lower_bounds: np.ndarray,
        upper_bounds: np.ndarray,
        nominal_target: float,
        tolerance: float = 0.05,
    ) -> dict[str, Any]:
        """Calculate empirical coverage and compare against nominal target."""
        valid_mask = ~np.isnan(y_true) & ~np.isnan(lower_bounds) & ~np.isnan(upper_bounds)
        if not np.any(valid_mask):
            return {
                "nominal_target": nominal_target,
                "empirical_coverage": 0.0,
                "is_well_calibrated": False,
                "error_delta": -nominal_target,
            }

        covered = (y_true[valid_mask] >= lower_bounds[valid_mask]) & (
            y_true[valid_mask] <= upper_bounds[valid_mask]
        )
        emp_coverage = float(np.mean(covered))
        error_delta = float(emp_coverage - nominal_target)
        is_calibrated = abs(error_delta) <= tolerance

        return {
            "nominal_target": nominal_target,
            "empirical_coverage": round(emp_coverage, 4),
            "is_well_calibrated": is_calibrated,
            "error_delta": round(error_delta, 4),
            "observations_evaluated": int(np.sum(valid_mask)),
        }


class ModelGovernance:
    """Enforces deployment policies, audit gates, and model promotion governance rules."""

    OFFICIAL_WAPE_THRESHOLD: float = 0.2800

    @classmethod
    def evaluate_model_promotion(
        cls,
        candidate_model_id: str,
        candidate_wape: float,
        baseline_wape: float,
        drift_detected: bool,
        human_approved: bool = False,
        artifact_sha256_verified: bool = True,
    ) -> tuple[bool, str]:
        """Evaluates whether a candidate model can be promoted to production.

        CRITICAL GOVERNANCE PRINCIPLES:
        1. Drift alone does NOT trigger automated promotion; retraining under drift
           strictly requires formal human merchant / data scientist approval.
        2. Candidate model must pass the official WAPE threshold (<= 0.2800).
        3. Candidate model must demonstrate equal or superior holdout performance
           over the active production model.
        4. Cryptographic artifact integrity must be verified.
        """
        # Rule 1: Cryptographic Integrity Gate
        if not artifact_sha256_verified:
            logger.error("Promotion rejected for %s: Cryptographic SHA-256 verification failed.", candidate_model_id)
            return False, "Model promotion REJECTED: Cryptographic SHA-256 verification failed."

        # Rule 2: Official WAPE Contract Gate
        if candidate_wape > cls.OFFICIAL_WAPE_THRESHOLD:
            msg = (
                f"Model promotion REJECTED: Candidate holdout WAPE ({candidate_wape:.4f}) "
                f"fails official threshold ({cls.OFFICIAL_WAPE_THRESHOLD:.4f})."
            )
            logger.warning(msg)
            return False, msg

        # Rule 3: Benchmark Superiority Gate
        if candidate_wape > baseline_wape:
            msg = (
                f"Model promotion REJECTED: Candidate WAPE ({candidate_wape:.4f}) "
                f"regresses against active baseline ({baseline_wape:.4f})."
            )
            logger.warning(msg)
            return False, msg

        # Rule 4: Drift Governance Safeguard (CRITICAL SPECIFICATION REQUIREMENT)
        # "Do not automatically promote a model solely because drift is detected."
        if drift_detected and not human_approved:
            msg = (
                "Model promotion BLOCKED: Feature/data drift detected. "
                "Automated promotion is strictly prohibited under detected drift without explicit "
                "human sign-off from lead merchandising and data science personnel."
            )
            logger.warning(msg)
            return False, msg

        logger.info(
            "Model promotion APPROVED for %s (Candidate WAPE: %.4f vs Baseline: %.4f).",
            candidate_model_id,
            candidate_wape,
            baseline_wape,
        )
        return True, "Model promotion APPROVED: Satisfies official WAPE target, benchmark superiority, and governance safeguards."


# Global telemetry singleton
telemetry = TelemetryTracker()
