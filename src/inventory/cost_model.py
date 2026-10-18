"""Cost parameter modeling for Newsvendor Inventory Optimization.

Provides explicit understock (Cu) and overstock (Co) cost derivation,
critical ratio calculation, validation, and multi-scenario analysis.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CostScenario(str, Enum):
    """Pre-defined standard retail inventory cost scenarios."""
    CONSERVATIVE = "CONSERVATIVE"   # Low margin / high markdown penalty (protects working capital)
    BASE = "BASE"                   # Standard balanced retail department benchmark
    AGGRESSIVE = "AGGRESSIVE"       # High margin / high lost-goodwill stockout penalty
    CUSTOM = "CUSTOM"               # User-provided explicit Cu and Co


@dataclass
class SKUCostParameters:
    """Validated economic cost parameters for an individual SKU."""
    sku_id: str
    base_price: float
    understock_cost: float       # Cu: cost of one unit of unsatisfied demand (lost profit + goodwill)
    overstock_cost: float        # Co: cost of one unit of unsold inventory (procurement - salvage + holding)
    critical_ratio: float        # Cu / (Cu + Co)
    scenario: CostScenario
    assumptions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.understock_cost <= 0:
            raise ValueError(f"Understock cost Cu must be strictly positive, got {self.understock_cost}")
        if self.overstock_cost <= 0:
            raise ValueError(f"Overstock cost Co must be strictly positive, got {self.overstock_cost}")
        if not (0.0 < self.critical_ratio < 1.0):
            raise ValueError(f"Critical ratio must be in (0, 1), got {self.critical_ratio}")


class CostModel:
    """Derives and validates economic cost parameters for cold-start inventory optimization.

    Under the single-period newsvendor framework:
    - Cu = (Selling Price - Purchase Cost) + Lost Goodwill Penalty
    - Co = (Purchase Cost - Salvage Markdown Value) + Storage/Holding Cost
    - Critical Ratio (CR) = Cu / (Cu + Co)
    """

    # Scenario parameters expressed as fractions of retail selling price (P)
    SCENARIO_CONFIGS = {
        CostScenario.CONSERVATIVE: {
            "description": "Margin-constrained / High markdown penalty (Conservative buy)",
            "gross_margin_rate": 0.35,     # Purchase Cost = 65% of P
            "salvage_rate_of_cost": 0.20,  # Salvage = 20% of cost (deep clearance markdown)
            "holding_rate_of_cost": 0.10,  # Holding/liquidation cost = 10% of cost
            "goodwill_rate_of_price": 0.0, # Zero lost goodwill penalty
        },
        CostScenario.BASE: {
            "description": "Balanced standard retail benchmark",
            "gross_margin_rate": 0.50,     # Purchase Cost = 50% of P
            "salvage_rate_of_cost": 0.40,  # Salvage = 40% of cost (secondary channel recovery)
            "holding_rate_of_cost": 0.05,  # Holding/handling = 5% of cost
            "goodwill_rate_of_price": 0.05,# 5% lost customer lifetime goodwill penalty
        },
        CostScenario.AGGRESSIVE: {
            "description": "High margin / High stockout penalty (Capture all launch momentum)",
            "gross_margin_rate": 0.60,     # Purchase Cost = 40% of P
            "salvage_rate_of_cost": 0.50,  # Salvage = 50% of cost (outlet/factory store recovery)
            "holding_rate_of_cost": 0.05,  # Holding = 5% of cost
            "goodwill_rate_of_price": 0.15,# 15% high brand churn / lost customer penalty
        },
    }

    @classmethod
    def calculate_critical_ratio(cls, understock_cost: float, overstock_cost: float) -> float:
        """Calculates the Newsvendor critical ratio: Cu / (Cu + Co)."""
        if understock_cost <= 0 or overstock_cost <= 0:
            raise ValueError(
                f"Costs must be strictly positive. Got Cu={understock_cost}, Co={overstock_cost}"
            )
        return float(understock_cost / (understock_cost + overstock_cost))

    @classmethod
    def derive_sku_costs(
        cls,
        sku_id: str,
        base_price: float,
        scenario: CostScenario = CostScenario.BASE,
        custom_cu: float | None = None,
        custom_co: float | None = None,
    ) -> SKUCostParameters:
        """Derives validated cost parameters for a SKU under specified scenario or custom values."""
        price = max(1.0, float(base_price))

        if custom_cu is not None and custom_co is not None:
            cu = float(custom_cu)
            co = float(custom_co)
            cr = cls.calculate_critical_ratio(cu, co)
            return SKUCostParameters(
                sku_id=sku_id,
                base_price=price,
                understock_cost=round(cu, 4),
                overstock_cost=round(co, 4),
                critical_ratio=round(cr, 6),
                scenario=CostScenario.CUSTOM,
                assumptions={
                    "source": "explicit_user_input",
                    "custom_cu": cu,
                    "custom_co": co,
                },
            )

        if scenario not in cls.SCENARIO_CONFIGS:
            raise ValueError(f"Unknown cost scenario: {scenario}. Available: {list(cls.SCENARIO_CONFIGS.keys())}")

        cfg = cls.SCENARIO_CONFIGS[scenario]
        margin_rate = cfg["gross_margin_rate"]
        salvage_rate = cfg["salvage_rate_of_cost"]
        holding_rate = cfg["holding_rate_of_cost"]
        goodwill_rate = cfg["goodwill_rate_of_price"]

        unit_cost = price * (1.0 - margin_rate)
        salvage_val = unit_cost * salvage_rate
        holding_val = unit_cost * holding_rate
        goodwill_val = price * goodwill_rate

        # Cu = Lost gross profit + goodwill
        cu = (price - unit_cost) + goodwill_val
        # Co = Unit Cost - Salvage Value + Holding Cost
        co = (unit_cost - salvage_val) + holding_val
        cr = cls.calculate_critical_ratio(cu, co)

        return SKUCostParameters(
            sku_id=sku_id,
            base_price=price,
            understock_cost=round(cu, 4),
            overstock_cost=round(co, 4),
            critical_ratio=round(cr, 6),
            scenario=scenario,
            assumptions={
                "description": cfg["description"],
                "gross_margin_rate": margin_rate,
                "unit_procurement_cost": round(unit_cost, 2),
                "salvage_markdown_value": round(salvage_val, 2),
                "holding_handling_cost": round(holding_val, 2),
                "goodwill_penalty": round(goodwill_val, 2),
            },
        )
