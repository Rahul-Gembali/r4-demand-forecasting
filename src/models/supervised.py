"""Supervised Cold-Start Demand Forecasting Engine using CatBoost / GBDT.

Implements leakage-safe SKU-level dataset building, objective comparison,
hyperparameter tuning, model serialization, and unified prediction interface.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import catboost as cb
import numpy as np
import pandas as pd

from src.core.logging import logger


class ModelIntegrityError(Exception):
    """Raised when model artifact integrity verification fails (e.g. SHA-256 mismatch)."""
    pass


@dataclass
class DatasetSplits:
    """SKU-level partitioned datasets."""
    df_train: pd.DataFrame
    df_val: pd.DataFrame
    df_test: pd.DataFrame
    train_skus: list[str]
    val_skus: list[str]
    test_skus: list[str]


@dataclass
class SKUWeeklyForecast:
    """Output for a single SKU across introductory weeks 1 through 8."""
    sku_id: str
    weekly_forecast: list[float]      # Length 8
    cumulative_8w_forecast: float
    model_version: str
    feature_summary: dict[str, Any]
    # Prediction intervals
    weekly_lower_80: list[float] = field(default_factory=list)
    weekly_upper_80: list[float] = field(default_factory=list)
    weekly_lower_90: list[float] = field(default_factory=list)
    weekly_upper_90: list[float] = field(default_factory=list)
    cumul_lower_80: float = 0.0
    cumul_upper_80: float = 0.0
    cumul_lower_90: float = 0.0
    cumul_upper_90: float = 0.0


class SupervisedDatasetBuilder:
    """Constructs leakage-safe training panels with strict SKU-level partitioning."""

    FEATURE_COLUMNS = [
        "launch_week_age",
        "category",
        "subcategory",
        "colour",
        "material",
        "brand",
        "brand_tier",
        "price_band",
        "base_price",
        "log_base_price",
        "launch_month",
        "sin_launch_month",
        "cos_launch_month",
        "marketing_flag",
        "is_holiday_week",
        "week_of_year",
        "sin_week_of_year",
        "cos_week_of_year",
    ]

    CATEGORICAL_COLUMNS = [
        "category",
        "subcategory",
        "colour",
        "material",
        "brand",
        "brand_tier",
        "price_band",
    ]

    NUMERICAL_COLUMNS = [
        "launch_week_age",
        "base_price",
        "log_base_price",
        "launch_month",
        "sin_launch_month",
        "cos_launch_month",
        "marketing_flag",
        "is_holiday_week",
        "week_of_year",
        "sin_week_of_year",
        "cos_week_of_year",
    ]

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed

    def aggregate_sku_week_panel(self, df_train_features: pd.DataFrame) -> pd.DataFrame:
        """Aggregates store-level rows into an enterprise-level SKU-Week observation panel."""
        logger.info("Aggregating %d rows into SKU-Week panel...", len(df_train_features))

        group_cols = [
            "sku_id",
            "launch_week_age",
            "category",
            "subcategory",
            "colour",
            "material",
            "brand",
            "brand_tier",
            "price_band",
            "base_price",
            "log_base_price",
            "launch_month",
            "sin_launch_month",
            "cos_launch_month",
            "marketing_flag",
            "is_holiday_week",
            "week_of_year",
            "sin_week_of_year",
            "cos_week_of_year",
        ]

        sku_week = (
            df_train_features.groupby(group_cols, observed=True)["units_sold"]
            .sum()
            .reset_index()
        )
        # Ensure non-negativity
        sku_week["units_sold"] = np.maximum(0.0, sku_week["units_sold"])

        logger.info("Created SKU-Week panel: %d records across %d unique SKUs.",
                    len(sku_week), sku_week["sku_id"].nunique())
        return sku_week

    def split_by_sku(
        self,
        df_panel: pd.DataFrame,
        train_ratio: float = 0.6667,   # ~800 SKUs
        val_ratio: float = 0.1667,     # ~200 SKUs
        test_ratio: float = 0.1666,    # ~200 SKUs
    ) -> DatasetSplits:
        """Splits data strictly at SKU-level to prevent launch curve leakage."""
        np.random.seed(self.random_seed)
        unique_skus = np.array(df_panel["sku_id"].unique())
        np.random.shuffle(unique_skus)

        n_total = len(unique_skus)
        n_train = int(n_total * train_ratio)
        n_val = int(n_total * val_ratio)

        train_skus = list(unique_skus[:n_train])
        val_skus = list(unique_skus[n_train : n_train + n_val])
        test_skus = list(unique_skus[n_train + n_val :])

        df_train = df_panel[df_panel["sku_id"].isin(train_skus)].copy()
        df_val = df_panel[df_panel["sku_id"].isin(val_skus)].copy()
        df_test = df_panel[df_panel["sku_id"].isin(test_skus)].copy()

        logger.info(
            "SKU-level split created: Train=%d SKUs (%d rows), Val=%d SKUs (%d rows), Test=%d SKUs (%d rows)",
            len(train_skus), len(df_train), len(val_skus), len(df_val), len(test_skus), len(df_test),
        )
        return DatasetSplits(
            df_train=df_train,
            df_val=df_val,
            df_test=df_test,
            train_skus=train_skus,
            val_skus=val_skus,
            test_skus=test_skus,
        )


class CatBoostForecaster:
    """Supervised CatBoost model for 8-week cold-start retail demand forecasting."""

    # Map legacy / alternative objective aliases to CatBoost loss functions
    OBJECTIVE_MAP = {
        "regression_l1": "MAE",
        "l1": "MAE",
        "mae": "MAE",
        "regression": "RMSE",
        "l2": "RMSE",
        "rmse": "RMSE",
        "poisson": "Poisson",
        "huber": "Huber:delta=1.5",
    }

    def __init__(
        self,
        objective: str = "MAE",
        target_transform: Literal["raw", "log1p"] = "raw",
        iterations: int = 250,
        learning_rate: float = 0.05,
        depth: int = 6,
        l2_leaf_reg: float = 3.0,
        random_seed: int = 42,
        **kwargs: Any,
    ):
        # Normalize objective
        mapped_obj = self.OBJECTIVE_MAP.get(objective.lower(), objective)
        self.objective = mapped_obj
        self.target_transform = target_transform
        # Map n_estimators if passed from LightGBM alias
        if "n_estimators" in kwargs:
            iterations = kwargs["n_estimators"]
        self.iterations = iterations
        self.learning_rate = learning_rate
        self.depth = depth
        self.l2_leaf_reg = l2_leaf_reg
        self.random_seed = random_seed
        self.kwargs = kwargs

        self.model: cb.CatBoostRegressor | None = None
        self.feature_columns: list[str] = SupervisedDatasetBuilder.FEATURE_COLUMNS.copy()
        self.categorical_columns: list[str] = SupervisedDatasetBuilder.CATEGORICAL_COLUMNS.copy()
        self.is_fitted: bool = False

    def _transform_target(self, y: np.ndarray) -> np.ndarray:
        """Applies configured forward target transform."""
        if self.target_transform == "log1p":
            return np.log1p(np.maximum(0.0, y))
        return np.maximum(0.0, y)

    def _inverse_transform_target(self, y_hat: np.ndarray) -> np.ndarray:
        """Inverts target transform and enforces non-negativity."""
        if self.target_transform == "log1p":
            return np.maximum(0.0, np.expm1(y_hat))
        return np.maximum(0.0, y_hat)

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocesses feature columns into DataFrame ready for CatBoost."""
        df_out = pd.DataFrame(index=df.index)

        # Process categoricals: fill nulls with sentinel and cast to str
        for col in self.categorical_columns:
            if col in df.columns:
                df_out[col] = df[col].fillna("_MISSING_").astype(str)
            else:
                df_out[col] = "_MISSING_"

        # Process numericals: fill nulls with 0.0
        for col in self.feature_columns:
            if col not in self.categorical_columns:
                if col in df.columns:
                    df_out[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                else:
                    df_out[col] = 0.0

        # Ensure exact column ordering
        return df_out[self.feature_columns]

    def fit(
        self,
        df_train: pd.DataFrame,
        df_val: pd.DataFrame | None = None,
    ) -> "CatBoostForecaster":
        """Trains CatBoost model with early stopping on validation split."""
        logger.info(
            "Fitting CatBoostForecaster (Objective: %s, Transform: %s, Depth: %d, LR: %.3f)...",
            self.objective, self.target_transform, self.depth, self.learning_rate
        )

        X_train = self.prepare_features(df_train)
        y_train = self._transform_target(df_train["units_sold"].to_numpy())

        eval_set = None
        early_stopping = None
        if df_val is not None and not df_val.empty:
            X_val = self.prepare_features(df_val)
            y_val = self._transform_target(df_val["units_sold"].to_numpy())
            eval_set = (X_val, y_val)
            early_stopping = 25

        # Choose metric for validation monitoring
        eval_metric = "MAE" if "MAE" in self.objective else "RMSE"

        self.model = cb.CatBoostRegressor(
            loss_function=self.objective,
            eval_metric=eval_metric,
            iterations=self.iterations,
            learning_rate=self.learning_rate,
            depth=self.depth,
            l2_leaf_reg=self.l2_leaf_reg,
            random_seed=self.random_seed,
            cat_features=self.categorical_columns,
            early_stopping_rounds=early_stopping,
            verbose=0,
        )

        self.model.fit(
            X_train,
            y_train,
            eval_set=eval_set,
            verbose=False,
        )
        self.is_fitted = True
        logger.info("CatBoost model fitting complete. Best iteration: %s",
                    getattr(self.model, "get_best_iteration", lambda: self.iterations)())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predicts non-negative demand values."""
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Model is not fitted.")

        X = self.prepare_features(df)
        raw_preds = self.model.predict(X)
        clean_preds = self._inverse_transform_target(raw_preds)
        return np.maximum(0.0, clean_preds)

    def save_artifact(self, artifact_dir: Path) -> None:
        """Serializes trained model artifact, configuration, and feature schema."""
        artifact_dir.mkdir(parents=True, exist_ok=True)

        model_path = artifact_dir / "catboost_model.cbm"
        self.model.save_model(str(model_path))

        # Cryptographic integrity checksum of serialized weights
        sha256_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()

        best_iter = None
        if hasattr(self.model, "get_best_iteration"):
            try:
                best_iter = int(self.model.get_best_iteration())
            except Exception:
                best_iter = self.iterations

        config = {
            "model_type": "CatBoostRegressor",
            "objective": self.objective,
            "target_transform": self.target_transform,
            "iterations": self.iterations,
            "learning_rate": self.learning_rate,
            "depth": self.depth,
            "l2_leaf_reg": self.l2_leaf_reg,
            "random_seed": self.random_seed,
            "feature_columns": self.feature_columns,
            "categorical_columns": self.categorical_columns,
            "best_iteration": best_iter,
            "model_version": "v1.0.0-catboost-coldstart",
            "sha256_checksum": sha256_digest,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        with open(artifact_dir / "model_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        # Feature schema description
        feature_schema = {
            "feature_count": len(self.feature_columns),
            "features": [
                {
                    "name": col,
                    "type": "categorical" if col in self.categorical_columns else "numerical",
                    "role": "introductory_launch_curve_feature"
                }
                for col in self.feature_columns
            ]
        }
        with open(artifact_dir / "feature_schema.json", "w", encoding="utf-8") as f:
            json.dump(feature_schema, f, indent=2)

        logger.info("Saved complete model artifact [SHA256: %s] to: %s", sha256_digest[:12], artifact_dir)

    @classmethod
    def load_artifact(cls, artifact_dir: Path, verify_integrity: bool = True) -> "CatBoostForecaster":
        """Loads serialized model artifact from directory with cryptographic integrity verification."""
        config_path = artifact_dir / "model_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Model configuration file missing: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        model_weights_path = artifact_dir / "catboost_model.cbm"
        if not model_weights_path.exists():
            raise FileNotFoundError(f"Model weights file missing: {model_weights_path}")

        # Cryptographic artifact integrity check
        if verify_integrity and "sha256_checksum" in config:
            expected_sha = config["sha256_checksum"]
            actual_sha = hashlib.sha256(model_weights_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ModelIntegrityError(
                    f"Model artifact '{model_weights_path}' failed cryptographic integrity verification. "
                    f"Expected SHA256: {expected_sha}, got: {actual_sha}. Artifact is corrupted or tampered."
                )

        instance = cls(
            objective=config["objective"],
            target_transform=config["target_transform"],
            iterations=config["iterations"],
            learning_rate=config["learning_rate"],
            depth=config.get("depth", 6),
            l2_leaf_reg=config.get("l2_leaf_reg", 3.0),
            random_seed=config["random_seed"],
        )
        instance.model = cb.CatBoostRegressor()
        instance.model.load_model(str(model_weights_path))
        instance.feature_columns = config["feature_columns"]
        instance.categorical_columns = config["categorical_columns"]
        instance.is_fitted = True
        return instance


# Backward compatibility alias
LightGBMForecaster = CatBoostForecaster


class ColdStartPredictor:
    """Production prediction interface for single SKU attributes and batch evaluations."""

    def __init__(
        self,
        forecaster: CatBoostForecaster,
        calibrator: Any = None,
        model_version: str = "v1.0.0-catboost",
    ):
        self.forecaster = forecaster
        self.calibrator = calibrator
        self.model_version = model_version

    @classmethod
    def from_artifact(cls, artifact_dir: Path) -> "ColdStartPredictor":
        """Factory initializing predictor from saved disk artifact."""
        forecaster = CatBoostForecaster.load_artifact(artifact_dir)

        # Check if calibrated uncertainty configuration is present
        calibrator = None
        cal_path = artifact_dir / "uncertainty_config.json"
        if cal_path.exists():
            try:
                from src.evaluation.uncertainty import ConformalIntervalCalibrator
                calibrator = ConformalIntervalCalibrator.load(cal_path)
            except Exception as e:
                logger.warning("Failed to load uncertainty calibrator from %s: %s", cal_path, e)

        return cls(forecaster=forecaster, calibrator=calibrator)

    def predict_sku(self, sku_attributes: dict[str, Any]) -> SKUWeeklyForecast:
        """Generates 8-week nonnegative point forecast and optional intervals for a single new SKU."""
        sku_id = str(sku_attributes.get("sku_id", "NEW_SKU"))
        base_price = float(sku_attributes.get("base_price", 49.99))
        launch_date_str = str(sku_attributes.get("launch_date", "2025-11-03"))
        launch_dt = pd.to_datetime(launch_date_str)

        records = []
        for w in range(1, 9):
            h_dt = launch_dt + pd.Timedelta(days=(w - 1) * 7)
            woy = int(h_dt.isocalendar().week)
            mkt = 1 if (bool(sku_attributes.get("has_marketing_support", True)) and w <= 4) else 0

            records.append({
                "sku_id": sku_id,
                "launch_week_age": w,
                "category": str(sku_attributes.get("category", "_MISSING_")),
                "subcategory": str(sku_attributes.get("subcategory", "_MISSING_")),
                "colour": str(sku_attributes.get("colour", "_MISSING_")),
                "material": str(sku_attributes.get("material", "_MISSING_")),
                "brand": str(sku_attributes.get("brand", "_MISSING_")),
                "brand_tier": str(sku_attributes.get("brand_tier", "_MISSING_")),
                "price_band": str(sku_attributes.get("price_band", "_MISSING_")),
                "base_price": base_price,
                "log_base_price": math.log1p(base_price),
                "launch_month": launch_dt.month,
                "sin_launch_month": round(math.sin(2.0 * math.pi * launch_dt.month / 12.0), 6),
                "cos_launch_month": round(math.cos(2.0 * math.pi * launch_dt.month / 12.0), 6),
                "marketing_flag": mkt,
                "is_holiday_week": int(sku_attributes.get("is_holiday_week", 0)),
                "week_of_year": woy,
                "sin_week_of_year": round(math.sin(2.0 * math.pi * woy / 52.0), 6),
                "cos_week_of_year": round(math.cos(2.0 * math.pi * woy / 52.0), 6),
            })

        df_sku = pd.DataFrame(records)
        preds = self.forecaster.predict(df_sku)
        clean_forecast = [max(0.0, round(float(p), 2)) for p in preds]
        cumul_pred = round(sum(clean_forecast), 2)

        # Compute prediction intervals if calibrator is present
        w_low_80, w_up_80 = [], []
        w_low_90, w_up_90 = [], []
        c_low_80, c_up_80 = 0.0, 0.0
        c_low_90, c_up_90 = 0.0, 0.0

        if self.calibrator is not None and getattr(self.calibrator, "is_calibrated", False):
            np_preds = np.array(clean_forecast)
            l80, u80 = self.calibrator.predict_weekly_intervals(np_preds, confidence_level=0.80)
            l90, u90 = self.calibrator.predict_weekly_intervals(np_preds, confidence_level=0.90)
            w_low_80, w_up_80 = l80.tolist(), u80.tolist()
            w_low_90, w_up_90 = l90.tolist(), u90.tolist()

            cl80, cu80 = self.calibrator.predict_cumulative_intervals(np.array([cumul_pred]), confidence_level=0.80)
            cl90, cu90 = self.calibrator.predict_cumulative_intervals(np.array([cumul_pred]), confidence_level=0.90)
            c_low_80, c_up_80 = float(cl80[0]), float(cu80[0])
            c_low_90, c_up_90 = float(cl90[0]), float(cu90[0])

        return SKUWeeklyForecast(
            sku_id=sku_id,
            weekly_forecast=clean_forecast,
            cumulative_8w_forecast=cumul_pred,
            model_version=self.model_version,
            feature_summary={
                "category": sku_attributes.get("category"),
                "subcategory": sku_attributes.get("subcategory"),
                "base_price": base_price,
                "brand_tier": sku_attributes.get("brand_tier"),
            },
            weekly_lower_80=w_low_80,
            weekly_upper_80=w_up_80,
            weekly_lower_90=w_low_90,
            weekly_upper_90=w_up_90,
            cumul_lower_80=c_low_80,
            cumul_upper_80=c_up_80,
            cumul_lower_90=c_low_90,
            cumul_upper_90=c_up_90,
        )

    def predict_batch(
        self,
        df_target_features: pd.DataFrame,
        include_intervals: bool = False,
    ) -> pd.DataFrame:
        """Batch predicts for 150 evaluation SKUs across weeks 1 to 8.

        Returns standard long-form dataframe:
        ['sku_id', 'horizon_week', 'predicted_sales', ...]
        """
        df_in = df_target_features.copy()
        preds = self.forecaster.predict(df_in)
        preds_clean = np.maximum(0.0, np.round(preds, 2))

        df_out = pd.DataFrame({
            "sku_id": df_in["sku_id"].astype(str),
            "horizon_week": df_in["launch_week_age"].astype(int),
            "predicted_sales": preds_clean,
        })

        if include_intervals and self.calibrator is not None and getattr(self.calibrator, "is_calibrated", False):
            l80, u80 = self.calibrator.predict_weekly_intervals(preds_clean, confidence_level=0.80)
            l90, u90 = self.calibrator.predict_weekly_intervals(preds_clean, confidence_level=0.90)
            df_out["lower_bound_80"] = l80
            df_out["upper_bound_80"] = u80
            df_out["lower_bound_90"] = l90
            df_out["upper_bound_90"] = u90

            # SKU-level cumulative predictions and bounds
            sku_cum_map = df_out.groupby("sku_id")["predicted_sales"].sum().to_dict()
            df_out["cumul_pred_8w"] = df_out["sku_id"].map(sku_cum_map)

            unique_skus = df_out["sku_id"].drop_duplicates()
            unique_cums = np.array([sku_cum_map[s] for s in unique_skus])

            cl80, cu80 = self.calibrator.predict_cumulative_intervals(unique_cums, confidence_level=0.80)
            cl90, cu90 = self.calibrator.predict_cumulative_intervals(unique_cums, confidence_level=0.90)

            map_cl80 = dict(zip(unique_skus, cl80, strict=False))
            map_cu80 = dict(zip(unique_skus, cu80, strict=False))
            map_cl90 = dict(zip(unique_skus, cl90, strict=False))
            map_cu90 = dict(zip(unique_skus, cu90, strict=False))

            df_out["cumul_lower_80"] = df_out["sku_id"].map(map_cl80)
            df_out["cumul_upper_80"] = df_out["sku_id"].map(map_cu80)
            df_out["cumul_lower_90"] = df_out["sku_id"].map(map_cl90)
            df_out["cumul_upper_90"] = df_out["sku_id"].map(map_cu90)

        # Validate output shape and non-negativity
        if len(df_out) != len(df_in):
            raise ValueError(f"Output shape mismatch: {len(df_out)} vs {len(df_in)}")
        if (df_out["predicted_sales"] < 0).any():
            raise ValueError("Negative predictions detected.")
        if df_out["predicted_sales"].isnull().any():
            raise ValueError("Null predictions detected.")

        return df_out
