"""Monitoring and Governance Endpoints."""

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import AuthenticatedUser, require_admin, require_viewer
from src.core.monitoring import DataDriftDetector, ModelGovernance, telemetry
from src.db.models import SKUModel
from src.db.session import get_db_session

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Governance"])


class ModelPromotionRequest(BaseModel):
    candidate_model_id: str
    candidate_wape: float = Field(..., ge=0.0, le=1.0)
    baseline_wape: float = Field(..., ge=0.0, le=1.0)
    drift_detected: bool = False
    human_approved: bool = False
    artifact_sha256_verified: bool = True


class ModelPromotionResponse(BaseModel):
    candidate_model_id: str
    is_promoted: bool
    verdict: str
    evaluation_criteria: dict[str, Any]


@router.get(
    "/telemetry",
    summary="Get API Latency and Throughput Telemetry",
)
async def get_telemetry(
    current_user: AuthenticatedUser = Depends(require_viewer),
) -> dict[str, Any]:
    """Retrieve runtime latency percentiles (p50, p95, p99), error rates, and request counts."""
    return telemetry.get_summary()


@router.get(
    "/drift",
    summary="Evaluate Feature and Data Drift",
)
async def evaluate_drift(
    current_user: AuthenticatedUser = Depends(require_viewer),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Evaluate Population Stability Index (PSI) and Total Variation Distance (TVD) between baseline and evaluation SKUs."""
    # Fetch historical (baseline) SKUs vs evaluation SKUs
    hist_stmt = select(SKUModel).where(SKUModel.is_evaluation_sku == False)  # noqa: E712
    eval_stmt = select(SKUModel).where(SKUModel.is_evaluation_sku == True)   # noqa: E712

    hist_skus = list((await session.execute(hist_stmt)).scalars().all())
    eval_skus = list((await session.execute(eval_stmt)).scalars().all())

    if not hist_skus or not eval_skus:
        return {
            "drift_detected": False,
            "message": "Insufficient data to compute drift across SKU cohorts.",
            "features": {},
        }

    hist_df = pd.DataFrame([
        {"base_price": float(s.base_price), "category": s.category, "brand_tier": s.brand_tier or "Standard"}
        for s in hist_skus
    ])
    eval_df = pd.DataFrame([
        {"base_price": float(s.base_price), "category": s.category, "brand_tier": s.brand_tier or "Standard"}
        for s in eval_skus
    ])

    detector = DataDriftDetector()
    results = detector.assess_feature_drift(
        baseline_df=hist_df,
        current_df=eval_df,
        continuous_cols=["base_price"],
        categorical_cols=["category", "brand_tier"],
    )
    return results


@router.post(
    "/governance/evaluate",
    response_model=ModelPromotionResponse,
    summary="Evaluate Model Promotion Eligibility (Governance Gate)",
)
async def evaluate_model_promotion_gate(
    payload: ModelPromotionRequest,
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ModelPromotionResponse:
    """Enforce strict governance rules:

    - Model cannot be automatically promoted solely because drift is detected (requires human approval).
    - Candidate WAPE must satisfy official target (<= 0.2800).
    - Candidate WAPE must beat active baseline WAPE.
    - Model artifact SHA-256 integrity must be verified.
    """
    is_promoted, reason = ModelGovernance.evaluate_model_promotion(
        candidate_model_id=payload.candidate_model_id,
        candidate_wape=payload.candidate_wape,
        baseline_wape=payload.baseline_wape,
        drift_detected=payload.drift_detected,
        human_approved=payload.human_approved,
        artifact_sha256_verified=payload.artifact_sha256_verified,
    )

    return ModelPromotionResponse(
        candidate_model_id=payload.candidate_model_id,
        is_promoted=is_promoted,
        verdict=reason,
        evaluation_criteria={
            "official_wape_threshold": ModelGovernance.OFFICIAL_WAPE_THRESHOLD,
            "candidate_wape": payload.candidate_wape,
            "baseline_wape": payload.baseline_wape,
            "drift_detected": payload.drift_detected,
            "human_approved": payload.human_approved,
            "artifact_sha256_verified": payload.artifact_sha256_verified,
        },
    )
