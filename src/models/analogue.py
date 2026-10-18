"""Analogue Retrieval and Similarity-Weighted Cold-Start Forecasting Engine."""

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.core.logging import logger


@dataclass
class AnalogueMatch:
    """Individual historical donor match result."""
    analogue_sku_id: str
    rank: int
    similarity_score: float
    category: str
    subcategory: str
    base_price: float
    brand_tier: str
    observed_curve: list[float]  # Length 8: W1..W8 realized sales


@dataclass
class AnalogueRetrievalResult:
    """Top-K retrieval result for a single query SKU."""
    query_sku_id: str
    top_k_matches: list[AnalogueMatch]
    weighted_forecast: list[float]  # Length 8
    aggregation_weights: list[float]
    donor_count: int


class AttributeSimilarityEngine:
    """Computes multidimensional attribute similarity between retail SKUs.

    Supports categorical matching, price proximity, circular month distance,
    and configurable feature weights.
    """

    DEFAULT_FEATURE_WEIGHTS = {
        "category": 0.25,
        "subcategory": 0.25,
        "base_price": 0.15,
        "brand_tier": 0.15,
        "colour": 0.05,
        "material": 0.05,
        "launch_month": 0.05,
        "marketing": 0.05,
    }

    def __init__(self, feature_weights: dict[str, float] | None = None):
        self.weights = feature_weights or self.DEFAULT_FEATURE_WEIGHTS.copy()
        # Normalize weights to sum to 1.0
        total_w = sum(self.weights.values())
        if total_w <= 0:
            raise ValueError("Total feature weights must be positive.")
        self.weights = {k: v / total_w for k, v in self.weights.items()}

        self.candidate_catalog: pd.DataFrame | None = None
        self.candidate_curves: dict[str, list[float]] = {}
        self.price_min: float = 1.0
        self.price_max: float = 200.0

    def fit_candidates(
        self,
        df_mature_attributes: pd.DataFrame,
        df_mature_sales: pd.DataFrame,
    ) -> "AttributeSimilarityEngine":
        """Indexes historical donor SKUs and their realized 8-week launch curves."""
        logger.info("Indexing %d candidate donor SKUs for analogue retrieval...", len(df_mature_attributes))
        self.candidate_catalog = df_mature_attributes.copy()
        self.candidate_catalog["sku_id"] = self.candidate_catalog["sku_id"].astype(str)

        # Price scaling bounds
        self.price_min = float(self.candidate_catalog["base_price"].min())
        self.price_max = float(self.candidate_catalog["base_price"].max())

        # Aggregate 8-week enterprise sales curve per candidate SKU
        if "launch_week_age" in df_mature_sales.columns:
            sku_week = (
                df_mature_sales.groupby(["sku_id", "launch_week_age"])["units_sold"]
                .sum()
                .reset_index()
            )
        else:
            # If raw sales without launch_week_age, join launch_date from catalog to compute launch_week_age
            sales_with_launch = pd.merge(
                df_mature_sales,
                self.candidate_catalog[["sku_id", "launch_date"]],
                on="sku_id",
                how="inner",
            )
            s_dt = pd.to_datetime(sales_with_launch["week_start_date"])
            l_dt = pd.to_datetime(sales_with_launch["launch_date"])
            sales_with_launch["launch_week_age"] = ((s_dt - l_dt).dt.days // 7) + 1
            w1_w8 = sales_with_launch[sales_with_launch["launch_week_age"].isin(range(1, 9))]
            sku_week = (
                w1_w8.groupby(["sku_id", "launch_week_age"])["units_sold"]
                .sum()
                .reset_index()
            )

        self.candidate_curves.clear()
        for sku_id, group in sku_week.groupby("sku_id"):
            w_map = dict(zip(group["launch_week_age"], group["units_sold"], strict=False))
            curve = [float(w_map.get(w, 0.0)) for w in range(1, 9)]
            self.candidate_curves[str(sku_id)] = curve

        logger.info("Indexed curves for %d unique donor SKUs.", len(self.candidate_curves))
        return self

    def compute_pair_similarity(self, query: dict[str, Any], candidate: dict[str, Any]) -> float:
        """Calculates normalized attribute similarity score in [0.0, 1.0]."""
        score = 0.0

        # 1. Category (Exact match)
        q_cat = str(query.get("category", "")).strip().lower()
        c_cat = str(candidate.get("category", "")).strip().lower()
        if q_cat and q_cat != "_unknown_" and q_cat == c_cat:
            score += self.weights.get("category", 0.0)

        # 2. Subcategory (Exact match)
        q_subcat = str(query.get("subcategory", "")).strip().lower()
        c_subcat = str(candidate.get("subcategory", "")).strip().lower()
        if q_subcat and q_subcat not in ["_unknown_", "missing"] and q_subcat == c_subcat:
            score += self.weights.get("subcategory", 0.0)

        # 3. Base Price Proximity (Ratio-based bounded difference)
        q_price = float(query.get("base_price", self.price_min))
        c_price = float(candidate.get("base_price", self.price_min))
        max_p = max(q_price, c_price, 0.01)
        price_sim = max(0.0, 1.0 - (abs(q_price - c_price) / max_p))
        score += self.weights.get("base_price", 0.0) * price_sim

        # 4. Brand Tier (Exact match)
        q_tier = str(query.get("brand_tier", "")).strip().lower()
        c_tier = str(candidate.get("brand_tier", "")).strip().lower()
        if q_tier and q_tier == c_tier:
            score += self.weights.get("brand_tier", 0.0)

        # 5. Colour (Exact match)
        q_col = str(query.get("colour", "")).strip().lower()
        c_col = str(candidate.get("colour", "")).strip().lower()
        if q_col and q_col not in ["_unknown_", "missing"] and q_col == c_col:
            score += self.weights.get("colour", 0.0)

        # 6. Material (Exact match)
        q_mat = str(query.get("material", "")).strip().lower()
        c_mat = str(candidate.get("material", "")).strip().lower()
        if q_mat and q_mat not in ["_unknown_", "missing"] and q_mat == c_mat:
            score += self.weights.get("material", 0.0)

        # 7. Launch Month Circular Proximity
        q_month = int(query.get("launch_month", 1))
        c_month = int(candidate.get("launch_month", 1))
        month_diff = min(abs(q_month - c_month), 12 - abs(q_month - c_month))
        month_sim = max(0.0, 1.0 - (month_diff / 6.0))
        score += self.weights.get("launch_month", 0.0) * month_sim

        # 8. Marketing Support
        q_mkt = bool(query.get("has_marketing_support", True))
        c_mkt = bool(candidate.get("has_marketing_support", True))
        if q_mkt == c_mkt:
            score += self.weights.get("marketing", 0.0)

        return round(score, 6)

    def retrieve_top_k(
        self,
        query_attributes: dict[str, Any],
        k: int = 5,
        exclude_sku_id: str | None = None,
        force_same_category: bool = True,
    ) -> list[AnalogueMatch]:
        """Retrieves top-K most similar historical SKUs."""
        if self.candidate_catalog is None:
            raise RuntimeError("Candidate catalog not fitted. Call fit_candidates() first.")

        query_sku = str(query_attributes.get("sku_id", ""))
        exclude_id = exclude_sku_id or query_sku
        q_cat = str(query_attributes.get("category", "")).strip()

        # Candidate pool selection
        candidates = self.candidate_catalog
        if exclude_id:
            candidates = candidates[candidates["sku_id"] != exclude_id]

        if force_same_category and q_cat and q_cat != "_UNKNOWN_":
            same_cat = candidates[candidates["category"] == q_cat]
            if len(same_cat) >= k:
                candidates = same_cat

        if candidates.empty:
            logger.warning("No candidates found for query SKU %s. Expanding pool.", query_sku)
            candidates = self.candidate_catalog[self.candidate_catalog["sku_id"] != exclude_id]

        # Compute similarities
        scored_candidates = []
        for _, cand_row in candidates.iterrows():
            cand_dict = cand_row.to_dict()
            cand_sku = str(cand_dict["sku_id"])
            if cand_sku not in self.candidate_curves:
                continue

            sim = self.compute_pair_similarity(query_attributes, cand_dict)
            scored_candidates.append((sim, cand_dict))

        # Sort descending by similarity
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_matches = scored_candidates[:k]

        results = []
        for rank, (sim_score, cand_dict) in enumerate(top_matches, start=1):
            cand_sku = str(cand_dict["sku_id"])
            results.append(
                AnalogueMatch(
                    analogue_sku_id=cand_sku,
                    rank=rank,
                    similarity_score=sim_score,
                    category=str(cand_dict.get("category", "")),
                    subcategory=str(cand_dict.get("subcategory", "")),
                    base_price=float(cand_dict.get("base_price", 0.0)),
                    brand_tier=str(cand_dict.get("brand_tier", "")),
                    observed_curve=self.candidate_curves.get(cand_sku, [0.0] * 8).copy(),
                )
            )

        return results


class AnalogueForecaster:
    """Generates cold-start forecasts by aggregating retrieved analogue curves."""

    def __init__(
        self,
        similarity_engine: AttributeSimilarityEngine,
        k: int = 5,
        temperature_power: float = 2.0,  # Power exponent for similarity weighting
    ):
        self.engine = similarity_engine
        self.k = k
        self.temperature_power = temperature_power

    def forecast_sku(
        self,
        query_attributes: dict[str, Any],
        exclude_sku_id: str | None = None,
    ) -> AnalogueRetrievalResult:
        """Retrieves top-K analogues and computes weighted 8-week launch forecast."""
        query_sku = str(query_attributes.get("sku_id", "UNKNOWN"))
        matches = self.engine.retrieve_top_k(
            query_attributes=query_attributes,
            k=self.k,
            exclude_sku_id=exclude_sku_id,
        )

        if not matches:
            return AnalogueRetrievalResult(
                query_sku_id=query_sku,
                top_k_matches=[],
                weighted_forecast=[0.0] * 8,
                aggregation_weights=[],
                donor_count=0,
            )

        # Compute power-scaled similarity weights
        raw_weights = [m.similarity_score ** self.temperature_power for m in matches]
        total_w = sum(raw_weights)

        if total_w > 0:
            norm_weights = [w / total_w for w in raw_weights]
        else:
            # Equal weighting if similarities are zero
            norm_weights = [1.0 / len(matches)] * len(matches)

        # Weighted combination of 8-week curves
        curves_matrix = np.array([m.observed_curve for m in matches])  # Shape (K, 8)
        weights_vector = np.array(norm_weights).reshape(-1, 1)        # Shape (K, 1)

        aggregated_curve = np.sum(curves_matrix * weights_vector, axis=0)  # Shape (8,)
        # Enforce non-negativity and round
        clean_forecast = [max(0.0, round(float(v), 2)) for v in aggregated_curve]

        return AnalogueRetrievalResult(
            query_sku_id=query_sku,
            top_k_matches=matches,
            weighted_forecast=clean_forecast,
            aggregation_weights=[round(float(w), 4) for w in norm_weights],
            donor_count=len(matches),
        )

    def forecast_dataframe(
        self,
        df_target_attributes: pd.DataFrame,
        exclude_self: bool = False,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Generates 8-week analogue forecasts and retrieval audit logs.

        Returns:
          - df_forecasts: Long format ['sku_id', 'horizon_week', 'predicted_sales', 'top_match_sku', 'top_similarity']
          - audit_records: Detailed JSON-serializable list of top-K matches per SKU.
        """
        forecast_rows = []
        audit_records = []
        unique_skus = df_target_attributes.drop_duplicates(subset=["sku_id"])

        for _, row in unique_skus.iterrows():
            q_dict = row.to_dict()
            sku_id = str(q_dict["sku_id"])
            exclude_id = sku_id if exclude_self else None

            res = self.forecast_sku(q_dict, exclude_sku_id=exclude_id)
            top_sku = res.top_k_matches[0].analogue_sku_id if res.top_k_matches else "NONE"
            top_sim = res.top_k_matches[0].similarity_score if res.top_k_matches else 0.0

            for w_idx, pred_val in enumerate(res.weighted_forecast, start=1):
                forecast_rows.append({
                    "sku_id": sku_id,
                    "horizon_week": w_idx,
                    "predicted_sales": max(0.0, float(pred_val)),
                    "top_match_sku": top_sku,
                    "top_similarity": top_sim,
                })

            audit_records.append(asdict(res))

        return pd.DataFrame(forecast_rows), audit_records
