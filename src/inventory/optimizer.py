"""Newsvendor Inventory Optimization Engine for R4 Cold-Start Products.

Implements single-period critical ratio optimization, expected cost calculation,
parametric and conformal quantile inversion, integer constraints, and sensitivity analysis.
"""

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Literal
import numpy as np
import scipy.stats as stats

from src.core.logging import logger
from src.inventory.constraints import InventoryConstraints
from src.inventory.cost_model import CostModel, CostScenario, SKUCostParameters


@dataclass
class BuyRecommendation:
    """Optimized initial purchase order recommendation for an individual SKU."""
    sku_id: str
    forecast_cumulative_8w: float
    recommended_buy_quantity: int          # Q*: Final constrained integer buy quantity
    unconstrained_continuous_q: float      # F^-1(CR) before operational constraints
    critical_ratio: float                  # Cu / (Cu + Co)
    understock_cost_cu: float
    overstock_cost_co: float
    expected_shortage_units: float         # E[max(D - Q, 0)]
    expected_shortage_cost: float          # Cu * E[max(D - Q, 0)]
    expected_excess_units: float           # E[max(Q - D, 0)]
    expected_excess_cost: float            # Co * E[max(Q - D, 0)]
    expected_total_cost: float             # Total expected newsvendor cost
    expected_fill_rate_pct: float          # 1 - (E[Shortage] / Mean Demand)
    cost_scenario: str
    demand_distribution_method: str
    active_constraints: dict[str, Any]
    assumptions: dict[str, Any]


class NewsvendorOptimizer:
    """Solves the single-period inventory optimization problem under demand uncertainty.

    Objective:
        Minimize Expected Cost = Cu * E[max(D - Q, 0)] + Co * E[max(Q - D, 0)]

    Critical Ratio:
        CR = Cu / (Cu + Co)
    """

    def __init__(
        self,
        distribution_method: Literal["PARAMETRIC_NORMAL", "CONFORMAL_EMPIRICAL"] = "PARAMETRIC_NORMAL",
    ):
        self.distribution_method = distribution_method

    def _calculate_normal_loss(
        self, q: float, mu: float, sigma: float
    ) -> tuple[float, float]:
        """Calculates expected shortage and excess under Normal(mu, sigma) demand."""
        if mu <= 0.0 and sigma <= 1e-4:
            return 0.0, max(0.0, float(q))

        sigma_safe = max(1e-4, float(sigma))
        z = (q - mu) / sigma_safe

        phi_z = stats.norm.pdf(z)
        Phi_z = stats.norm.cdf(z)

        # Standard normal loss function L(z) = phi(z) - z * (1 - Phi(z))
        unit_shortage = sigma_safe * (phi_z - z * (1.0 - Phi_z))
        exp_shortage = max(0.0, float(unit_shortage))
        exp_excess = max(0.0, float(q - mu + exp_shortage))

        return exp_shortage, exp_excess

    def evaluate_expected_cost(
        self,
        q: float,
        mu: float,
        sigma: float,
        cu: float,
        co: float,
    ) -> tuple[float, float, float, float]:
        """Returns (expected_shortage, expected_excess, expected_shortage_cost, expected_total_cost)."""
        exp_shortage, exp_excess = self._calculate_normal_loss(q, mu, sigma)
        shortage_cost = cu * exp_shortage
        excess_cost = co * exp_excess
        total_cost = shortage_cost + excess_cost
        return exp_shortage, exp_excess, shortage_cost, total_cost

    def optimize_sku(
        self,
        sku_id: str,
        cumulative_demand_mean: float,
        cumulative_demand_lower_90: float,
        cumulative_demand_upper_90: float,
        base_price: float,
        scenario: CostScenario = CostScenario.BASE,
        custom_cu: float | None = None,
        custom_co: float | None = None,
        constraints: InventoryConstraints | None = None,
    ) -> BuyRecommendation:
        """Solves optimal buy quantity for an individual SKU over the 8-week horizon."""
        mu = max(0.0, float(cumulative_demand_mean))
        lb90 = max(0.0, float(cumulative_demand_lower_90))
        ub90 = max(lb90, float(cumulative_demand_upper_90))

        # Approximate sigma from calibrated 90% conformal interval (z_0.95 = 1.644853)
        if ub90 > lb90:
            sigma = max(1.0, (ub90 - lb90) / (2.0 * 1.644853))
        else:
            sigma = max(1.0, 0.15 * mu)

        # Economic costs and critical ratio
        cost_params = CostModel.derive_sku_costs(
            sku_id=sku_id,
            base_price=base_price,
            scenario=scenario,
            custom_cu=custom_cu,
            custom_co=custom_co,
        )
        cu = cost_params.understock_cost
        co = cost_params.overstock_cost
        cr = cost_params.critical_ratio

        # Zero demand edge case
        if mu == 0.0:
            return BuyRecommendation(
                sku_id=sku_id,
                forecast_cumulative_8w=0.0,
                recommended_buy_quantity=0,
                unconstrained_continuous_q=0.0,
                critical_ratio=round(cr, 4),
                understock_cost_cu=cu,
                overstock_cost_co=co,
                expected_shortage_units=0.0,
                expected_shortage_cost=0.0,
                expected_excess_units=0.0,
                expected_excess_cost=0.0,
                expected_total_cost=0.0,
                expected_fill_rate_pct=100.0,
                cost_scenario=cost_params.scenario.value,
                demand_distribution_method=self.distribution_method,
                active_constraints={},
                assumptions={"note": "Zero expected demand results in zero order."},
            )

        # 1. Optimal unconstrained continuous quantity F^-1(CR)
        z_cr = float(stats.norm.ppf(cr))
        continuous_q = max(0.0, mu + z_cr * sigma)

        # 2. Define cost evaluation closure for operational constraints
        def cost_evaluator(candidate_q: int) -> float:
            _, _, _, t_cost = self.evaluate_expected_cost(
                q=float(candidate_q), mu=mu, sigma=sigma, cu=cu, co=co
            )
            return t_cost

        # 3. Apply operational constraints (MOQ, Case Pack, Cap, Integer)
        active_constraints_map = {}
        if constraints is not None:
            final_q = constraints.apply(continuous_q, cost_eval_fn=cost_evaluator)
            if constraints.min_order_quantity:
                active_constraints_map["min_order_quantity"] = constraints.min_order_quantity
            if constraints.case_pack_size:
                active_constraints_map["case_pack_size"] = constraints.case_pack_size
            if constraints.max_order_quantity:
                active_constraints_map["max_order_quantity"] = constraints.max_order_quantity
        else:
            final_q = max(0, int(round(continuous_q)))

        # 4. Final expected performance metrics at recommended quantity
        exp_shortage, exp_excess, exp_short_cost, exp_total_cost = self.evaluate_expected_cost(
            q=float(final_q), mu=mu, sigma=sigma, cu=cu, co=co
        )
        exp_excess_cost = co * exp_excess
        fill_rate = max(0.0, min(100.0, (1.0 - (exp_shortage / mu)) * 100.0)) if mu > 0 else 100.0

        return BuyRecommendation(
            sku_id=sku_id,
            forecast_cumulative_8w=round(mu, 2),
            recommended_buy_quantity=final_q,
            unconstrained_continuous_q=round(continuous_q, 2),
            critical_ratio=round(cr, 4),
            understock_cost_cu=round(cu, 2),
            overstock_cost_co=round(co, 2),
            expected_shortage_units=round(exp_shortage, 2),
            expected_shortage_cost=round(exp_short_cost, 2),
            expected_excess_units=round(exp_excess, 2),
            expected_excess_cost=round(exp_excess_cost, 2),
            expected_total_cost=round(exp_total_cost, 2),
            expected_fill_rate_pct=round(fill_rate, 2),
            cost_scenario=cost_params.scenario.value,
            demand_distribution_method=self.distribution_method,
            active_constraints=active_constraints_map,
            assumptions={
                **cost_params.assumptions,
                "sigma_8w": round(sigma, 2),
                "z_critical_ratio": round(z_cr, 4),
                "single_period_assumption": "Initial 8-week launch window evaluated as single purchase commitment.",
            },
        )

    def sensitivity_analysis(
        self,
        cumulative_demand_mean: float,
        cumulative_demand_lower_90: float,
        cumulative_demand_upper_90: float,
        base_price: float,
        critical_ratios: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Sweeps across critical ratio values to demonstrate quantity and cost sensitivity."""
        if critical_ratios is None:
            critical_ratios = [0.25, 0.35, 0.50, 0.60, 0.70, 0.80, 0.85]

        mu = max(0.0, float(cumulative_demand_mean))
        lb90 = max(0.0, float(cumulative_demand_lower_90))
        ub90 = max(lb90, float(cumulative_demand_upper_90))
        sigma = max(1.0, (ub90 - lb90) / (2.0 * 1.644853))

        results = []
        for cr in critical_ratios:
            # Calibrate dummy Cu/Co yielding exact CR with fixed price scale
            co = base_price * 0.35
            cu = (cr * co) / (1.0 - cr)

            z_cr = float(stats.norm.ppf(cr))
            q_opt = max(0, int(round(mu + z_cr * sigma)))
            exp_short, exp_excess, _, exp_cost = self.evaluate_expected_cost(
                q=float(q_opt), mu=mu, sigma=sigma, cu=cu, co=co
            )
            fill_rate = max(0.0, min(100.0, (1.0 - (exp_short / mu)) * 100.0)) if mu > 0 else 100.0

            results.append({
                "critical_ratio": round(cr, 2),
                "buy_quantity": q_opt,
                "safety_stock_units": int(q_opt - mu),
                "expected_shortage_units": round(exp_short, 2),
                "expected_excess_units": round(exp_excess, 2),
                "expected_fill_rate_pct": round(fill_rate, 2),
                "expected_total_cost": round(exp_cost, 2),
            })

        return results
