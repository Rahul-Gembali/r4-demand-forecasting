"""Operational inventory constraints for initial buy quantity optimization."""

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class InventoryConstraints:
    """Configurable physical and operational constraints on purchase orders."""
    min_order_quantity: int | None = None   # MOQ: Supplier minimum buy threshold
    case_pack_size: int | None = None       # Master carton / inner pack multiple
    max_order_quantity: int | None = None   # Warehouse space or capital budget ceiling
    lead_time_weeks: int | None = None      # Vendor delivery lead time
    shelf_life_weeks: int | None = None     # Perishability or seasonal phaseout window

    def apply(self, continuous_q: float, cost_eval_fn: Callable[[int], float] | None = None) -> int:
        """Applies configured operational constraints to unconstrained continuous quantity.

        Parameters
        ----------
        continuous_q : float
            Optimal continuous newsvendor quantity: F^-1(CR).
        cost_eval_fn : Callable[[int], float] | None
            Function returning expected total cost for a candidate integer quantity,
            used to resolve case-pack rounding (floor vs ceil) and MOQ thresholds.
        """
        # 1. Base non-negative integer rounding
        q = max(0, int(round(continuous_q)))

        # 2. Case-pack rounding (if configured)
        if self.case_pack_size is not None and self.case_pack_size > 1:
            cp = self.case_pack_size
            q_floor = (q // cp) * cp
            q_ceil = math.ceil(q / cp) * cp

            if cost_eval_fn is not None:
                cost_floor = cost_eval_fn(q_floor)
                cost_ceil = cost_eval_fn(q_ceil)
                q = q_floor if cost_floor <= cost_ceil else q_ceil
            else:
                # Default to nearest multiple
                q = q_floor if (q - q_floor) < (q_ceil - q) else q_ceil

        # 3. Minimum Order Quantity (MOQ) evaluation
        if self.min_order_quantity is not None and self.min_order_quantity > 0:
            moq = self.min_order_quantity
            if 0 < q < moq:
                if cost_eval_fn is not None:
                    cost_moq = cost_eval_fn(moq)
                    cost_zero = cost_eval_fn(0)
                    q = moq if cost_moq <= cost_zero else 0
                else:
                    # If demand justifies ordering more than half the MOQ, order MOQ
                    q = moq if q >= (moq / 2.0) else 0

        # 4. Maximum order cap
        if self.max_order_quantity is not None and self.max_order_quantity > 0:
            q = min(q, self.max_order_quantity)

        return max(0, int(q))
