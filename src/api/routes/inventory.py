"""Inventory Optimization and Newsvendor Buy Quantity Endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import AuthenticatedUser, require_operator
from src.api.schemas import (
    InventoryOptimizeItem,
    InventoryOptimizeRequest,
    InventoryOptimizeResponse,
)
from src.core.logging import get_logger
from src.db.models import InventoryRecommendationModel, SKUModel, WeeklyForecastModel
from src.db.repository import ForecastRepository
from src.db.session import get_db_session
from src.inventory.constraints import InventoryConstraints
from src.inventory.cost_model import CostScenario
from src.inventory.optimizer import NewsvendorOptimizer

logger = get_logger("api_inventory")
router = APIRouter(prefix="/inventory", tags=["Inventory Optimization"])


@router.post(
    "/optimize",
    response_model=InventoryOptimizeResponse,
    summary="Run Custom Newsvendor Buy Quantity Optimization Scenario",
)
async def optimize_inventory(
    payload: InventoryOptimizeRequest,
    current_user: AuthenticatedUser = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> InventoryOptimizeResponse:
    """Optimize initial order quantities under custom cost margins and operational packing constraints."""
    repo = ForecastRepository(session)
    run = await repo.get_forecast_run(payload.run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Forecast run '{payload.run_id}' not found.",
        )

    # Fetch base recommendations
    stmt = select(InventoryRecommendationModel).where(
        InventoryRecommendationModel.run_id == payload.run_id,
        InventoryRecommendationModel.scenario == "BASE",
    )
    if payload.sku_ids:
        stmt = stmt.where(InventoryRecommendationModel.sku_id.in_(payload.sku_ids))

    base_recs = list((await session.execute(stmt)).scalars().all())
    if not base_recs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No base recommendations found for run '{payload.run_id}'.",
        )

    optimizer = NewsvendorOptimizer()
    constraints = InventoryConstraints(
        min_order_quantity=payload.min_order_quantity,
        case_pack_size=payload.case_pack_size,
    )

    scenario_enum = CostScenario.CUSTOM
    if payload.scenario_name.upper() in CostScenario.__members__:
        scenario_enum = CostScenario[payload.scenario_name.upper()]

    new_rec_models = []
    response_items = []
    total_units = 0
    total_cost = 0.0
    fill_rates = []

    # Batch retrieve true calibrated conformal bounds and SKU master prices (FL-08)
    sku_ids = [rec.sku_id for rec in base_recs]
    wf_stmt = select(WeeklyForecastModel).where(
        WeeklyForecastModel.run_id == payload.run_id,
        WeeklyForecastModel.sku_id.in_(sku_ids),
    )
    wf_rows = (await session.execute(wf_stmt)).scalars().all()
    wf_bounds_map: dict[str, tuple[float, float]] = {}
    for w in wf_rows:
        cur_low, cur_high = wf_bounds_map.get(w.sku_id, (0.0, 0.0))
        wf_bounds_map[w.sku_id] = (
            cur_low + float(w.lower_bound_90 or 0.0),
            cur_high + float(w.upper_bound_90 or 0.0),
        )

    sku_stmt = select(SKUModel).where(SKUModel.sku_id.in_(sku_ids))
    skus_rows = (await session.execute(sku_stmt)).scalars().all()
    sku_price_map = {s.sku_id: float(s.base_price) for s in skus_rows if s.base_price}

    for rec in base_recs:
        cu = payload.understock_cost_cu or float(rec.understock_cost_cu)
        co = payload.overstock_cost_co or float(rec.overstock_cost_co)
        bp = sku_price_map.get(rec.sku_id, (cu / 0.45 if cu > 0 else 50.0))

        # Use true cumulative conformal bounds when available (FL-08)
        if rec.sku_id in wf_bounds_map and wf_bounds_map[rec.sku_id][1] > 0:
            c_low, c_high = wf_bounds_map[rec.sku_id]
        else:
            c_low = float(rec.forecast_cumulative_8w) * 0.75
            c_high = float(rec.forecast_cumulative_8w) * 1.25

        opt_res = optimizer.optimize_sku(
            sku_id=rec.sku_id,
            cumulative_demand_mean=float(rec.forecast_cumulative_8w),
            cumulative_demand_lower_90=c_low,
            cumulative_demand_upper_90=c_high,
            base_price=bp,
            scenario=scenario_enum,
            custom_cu=cu,
            custom_co=co,
            constraints=constraints,
        )

        new_rec_models.append(
            {
                "sku_id": rec.sku_id,
                "scenario": payload.scenario_name,
                "forecast_cumulative_8w": rec.forecast_cumulative_8w,
                "recommended_buy_quantity": opt_res.recommended_buy_quantity,
                "unconstrained_quantity": opt_res.unconstrained_continuous_q,
                "critical_ratio": opt_res.critical_ratio,
                "understock_cost_cu": cu,
                "overstock_cost_co": co,
                "expected_shortage_units": opt_res.expected_shortage_units,
                "expected_excess_units": opt_res.expected_excess_units,
                "expected_total_cost": opt_res.expected_total_cost,
                "expected_fill_rate_pct": opt_res.expected_fill_rate_pct,
                "confidence_score": rec.confidence_score,
                "confidence_tier": rec.confidence_tier,
                "explanation_summary": rec.explanation_summary,
                "assumptions": {
                    "scenario": payload.scenario_name,
                    "min_order_quantity": payload.min_order_quantity,
                    "case_pack_size": payload.case_pack_size,
                },
            }
        )

        response_items.append(
            InventoryOptimizeItem(
                sku_id=rec.sku_id,
                scenario=payload.scenario_name,
                recommended_buy_quantity=opt_res.recommended_buy_quantity,
                critical_ratio=opt_res.critical_ratio,
                expected_total_cost=opt_res.expected_total_cost,
                expected_fill_rate_pct=opt_res.expected_fill_rate_pct,
            )
        )

        total_units += opt_res.recommended_buy_quantity
        total_cost += opt_res.expected_total_cost
        fill_rates.append(opt_res.expected_fill_rate_pct)

    # Persist optimized scenario
    await repo.save_inventory_recommendations(payload.run_id, new_rec_models)
    await session.commit()

    logger.info(
        f"Optimized {len(response_items)} SKUs for run [{payload.run_id}] "
        f"scenario '{payload.scenario_name}' (total buy units: {total_units})."
    )

    return InventoryOptimizeResponse(
        run_id=payload.run_id,
        scenario_name=payload.scenario_name,
        total_skus_optimized=len(response_items),
        total_buy_units=total_units,
        total_expected_cost=round(total_cost, 2),
        average_fill_rate_pct=round(sum(fill_rates) / len(fill_rates), 2) if fill_rates else 0.0,
        recommendations=response_items,
    )
