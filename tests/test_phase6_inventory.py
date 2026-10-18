"""Unit tests for Phase 6 Initial Inventory and Buy Quantity Optimization."""

import pytest

from src.inventory.constraints import InventoryConstraints
from src.inventory.cost_model import CostModel, CostScenario
from src.inventory.optimizer import NewsvendorOptimizer


def test_zero_demand_handling():
    optimizer = NewsvendorOptimizer()
    rec = optimizer.optimize_sku(
        sku_id="ZERO_DEMAND_SKU",
        cumulative_demand_mean=0.0,
        cumulative_demand_lower_90=0.0,
        cumulative_demand_upper_90=0.0,
        base_price=50.0,
        scenario=CostScenario.BASE,
    )
    assert rec.recommended_buy_quantity == 0
    assert rec.expected_shortage_units == 0.0
    assert rec.expected_excess_units == 0.0
    assert rec.expected_total_cost == 0.0
    assert rec.expected_fill_rate_pct == 100.0


def test_high_uncertainty_behavior():
    optimizer = NewsvendorOptimizer()
    mu = 500.0

    # Low uncertainty interval vs High uncertainty interval
    lb_low, ub_low = 480.0, 520.0     # sigma ~ 12
    lb_high, ub_high = 200.0, 800.0   # sigma ~ 182

    # Case 1: High Critical Ratio (CR = 0.77 > 0.50) -> Aggressive scenario
    rec_low_aggr = optimizer.optimize_sku(
        sku_id="SKU_LOW", cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb_low, cumulative_demand_upper_90=ub_low,
        base_price=100.0, scenario=CostScenario.AGGRESSIVE
    )
    rec_high_aggr = optimizer.optimize_sku(
        sku_id="SKU_HIGH", cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb_high, cumulative_demand_upper_90=ub_high,
        base_price=100.0, scenario=CostScenario.AGGRESSIVE
    )
    # Under high CR, higher uncertainty demands a larger buffer
    assert rec_high_aggr.recommended_buy_quantity > rec_low_aggr.recommended_buy_quantity

    # Case 2: Low Critical Ratio (CR = 0.37 < 0.50) -> Conservative scenario
    rec_low_cons = optimizer.optimize_sku(
        sku_id="SKU_LOW_C", cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb_low, cumulative_demand_upper_90=ub_low,
        base_price=100.0, scenario=CostScenario.CONSERVATIVE
    )
    rec_high_cons = optimizer.optimize_sku(
        sku_id="SKU_HIGH_C", cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb_high, cumulative_demand_upper_90=ub_high,
        base_price=100.0, scenario=CostScenario.CONSERVATIVE
    )
    # Under low CR, higher uncertainty induces stronger conservative trimming
    assert rec_high_cons.recommended_buy_quantity < rec_low_cons.recommended_buy_quantity


def test_zero_and_invalid_cost_handling():
    # Negative or zero costs must raise ValueError
    with pytest.raises(ValueError, match="strictly positive"):
        CostModel.calculate_critical_ratio(understock_cost=-10.0, overstock_cost=20.0)

    with pytest.raises(ValueError, match="strictly positive"):
        CostModel.calculate_critical_ratio(understock_cost=20.0, overstock_cost=0.0)

    with pytest.raises(ValueError, match="strictly positive"):
        CostModel.derive_sku_costs(
            sku_id="BAD_COST_SKU",
            base_price=50.0,
            custom_cu=0.0,
            custom_co=10.0,
        )


def test_integer_and_non_negativity_constraints():
    optimizer = NewsvendorOptimizer()
    rec = optimizer.optimize_sku(
        sku_id="TEST_INT",
        cumulative_demand_mean=123.456,
        cumulative_demand_lower_90=90.0,
        cumulative_demand_upper_90=160.0,
        base_price=45.0,
    )
    assert isinstance(rec.recommended_buy_quantity, int)
    assert rec.recommended_buy_quantity >= 0


def test_monotonic_behavior_with_critical_ratio():
    optimizer = NewsvendorOptimizer()
    mu = 300.0
    lb, ub = 250.0, 350.0

    # Step Cu upwards while keeping Co constant -> CR increases monotonically
    co_fixed = 10.0
    quantities = []
    for cu in [5.0, 10.0, 20.0, 40.0, 80.0]:
        rec = optimizer.optimize_sku(
            sku_id="MONOTONIC_SKU",
            cumulative_demand_mean=mu,
            cumulative_demand_lower_90=lb,
            cumulative_demand_upper_90=ub,
            base_price=50.0,
            custom_cu=cu,
            custom_co=co_fixed,
        )
        quantities.append(rec.recommended_buy_quantity)

    # Quantities must be strictly non-decreasing
    for idx in range(len(quantities) - 1):
        assert quantities[idx] <= quantities[idx + 1]
    assert quantities[-1] > quantities[0]


def test_case_pack_and_moq_constraints():
    optimizer = NewsvendorOptimizer()
    mu = 103.0
    lb, ub = 80.0, 130.0

    # Test Case Pack: multiple of 12
    constraints_cp = InventoryConstraints(case_pack_size=12)
    rec_cp = optimizer.optimize_sku(
        sku_id="CP_SKU",
        cumulative_demand_mean=mu,
        cumulative_demand_lower_90=lb,
        cumulative_demand_upper_90=ub,
        base_price=50.0,
        constraints=constraints_cp,
    )
    assert rec_cp.recommended_buy_quantity % 12 == 0

    # Test MOQ: demand is small (mu = 5), MOQ = 50
    # Cost of buying 50 units vs buying 0: buying 0 is cheaper than buying 10x demand
    constraints_moq = InventoryConstraints(min_order_quantity=50)
    rec_moq_small = optimizer.optimize_sku(
        sku_id="MOQ_SMALL_SKU",
        cumulative_demand_mean=5.0,
        cumulative_demand_lower_90=2.0,
        cumulative_demand_upper_90=8.0,
        base_price=50.0,
        constraints=constraints_moq,
    )
    assert rec_moq_small.recommended_buy_quantity == 0  # Rejects unprofitable MOQ

    # Test MOQ: demand is large (mu = 40), MOQ = 50 -> orders MOQ
    rec_moq_large = optimizer.optimize_sku(
        sku_id="MOQ_LARGE_SKU",
        cumulative_demand_mean=42.0,
        cumulative_demand_lower_90=35.0,
        cumulative_demand_upper_90=50.0,
        base_price=50.0,
        constraints=constraints_moq,
    )
    assert rec_moq_large.recommended_buy_quantity >= 50


def test_scenario_derivation_ordering():
    optimizer = NewsvendorOptimizer()
    mu = 600.0
    lb, ub = 450.0, 750.0

    rec_cons = optimizer.optimize_sku("S_SKU", mu, lb, ub, 120.0, scenario=CostScenario.CONSERVATIVE)
    rec_base = optimizer.optimize_sku("S_SKU", mu, lb, ub, 120.0, scenario=CostScenario.BASE)
    rec_aggr = optimizer.optimize_sku("S_SKU", mu, lb, ub, 120.0, scenario=CostScenario.AGGRESSIVE)

    assert rec_cons.critical_ratio < rec_base.critical_ratio < rec_aggr.critical_ratio
    assert rec_cons.recommended_buy_quantity < rec_base.recommended_buy_quantity < rec_aggr.recommended_buy_quantity


def test_sensitivity_analysis_structure():
    optimizer = NewsvendorOptimizer()
    table = optimizer.sensitivity_analysis(
        cumulative_demand_mean=500.0,
        cumulative_demand_lower_90=400.0,
        cumulative_demand_upper_90=600.0,
        base_price=80.0,
        critical_ratios=[0.30, 0.50, 0.70],
    )
    assert len(table) == 3
    assert table[0]["buy_quantity"] < table[1]["buy_quantity"] < table[2]["buy_quantity"]
    assert table[0]["expected_shortage_units"] > table[2]["expected_shortage_units"]
    assert table[0]["expected_excess_units"] < table[2]["expected_excess_units"]
    assert table[0]["expected_fill_rate_pct"] < table[2]["expected_fill_rate_pct"]
