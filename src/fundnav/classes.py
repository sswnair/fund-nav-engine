"""Share classes: splitting the fund's result between them, and each class's NAV.

The fund's result for the day (market moves, FX, income and shared expenses)
is split between the classes in proportion to their NAV at the previous
valuation point. Each class then bears its own fees. A class in another
currency is translated at the day's rate only for its NAV per share;
everything before that is in base currency.
"""

from __future__ import annotations

from typing import Mapping

from .accruals import accrue_percentage
from .models import ClassState, ClassValuation, ShareClass
from .money import round_half_up, round_money
from .perf_fee import performance_fee_accrual


def class_weights(navs: Mapping[str, float]) -> dict[str, float]:
    """Each class's share of the combined NAV, keyed like `navs`.

    Raises ValueError when a NAV is negative or the total is not positive.
    """
    if any(v < 0 for v in navs.values()):
        raise ValueError("a class NAV cannot be negative")
    total = sum(navs.values())
    if total <= 0:
        raise ValueError("total NAV must be positive")
    return {code: nav / total for code, nav in navs.items()}


def allocate(amount: float, weights: Mapping[str, float]) -> dict[str, float]:
    """Split an amount between classes by weight, in cents that add up exactly.

    The amount is rounded to cents, each class's share is rounded to cents,
    and whatever rounding leaves over goes to the class with the largest
    weight (the first one listed if two tie), so the parts always sum to the
    rounded amount.
    """
    total = round_money(amount)
    parts = {code: round_money(total * w) for code, w in weights.items()}
    largest = max(weights, key=lambda code: weights[code])
    parts[largest] = round_money(parts[largest] + total - sum(parts.values()))
    return parts


def nav_per_share(nav: float, units: float, fx_rate: float = 1.0, decimals: int = 4) -> float:
    """NAV per share in class currency.

    nav is in base currency and fx_rate converts base into class currency
    (units of class currency per one unit of base), so the result is
    nav * fx_rate / units, rounded half up to `decimals` places.

    Raises ValueError when units is not positive.
    """
    if units <= 0:
        raise ValueError(f"units must be positive, got {units}")
    return round_half_up(nav * fx_rate / units, decimals)


def value_class(
    share_class: ShareClass,
    state: ClassState,
    allocation: float,
    days: int,
    fx_rate: float = 1.0,
    nav_decimals: int = 4,
    day_count: int = 365,
) -> ClassValuation:
    """Value one share class for the day, before dealing.

    state is the class at the previous valuation point and allocation is its
    share of the day's result, both in base currency. The management fee
    accrues for `days` days on the NAV before fees, state.nav plus the
    allocation. The performance fee accrual is then recalculated in full on
    the gross NAV per share in class currency: the NAV before fees, less the
    management fee, plus the fee already accrued this period, over
    state.units. Adding the accrual back keeps the fee from being charged on
    itself. Only the accrual's change from yesterday comes off the NAV, and
    that change is negative when performance falls. A class without a
    performance fee has none.

    NAV is the NAV before fees less the management fee and the change in
    the performance fee accrual, and NAV per share is NAV over state.units
    in class currency. Base-currency amounts are rounded to cents.
    """
    nav_before = round_money(state.nav + allocation)
    management = accrue_percentage(nav_before, share_class.management_fee, days, day_count)

    accrued, change = 0.0, 0.0
    if share_class.performance_fee:
        gross = nav_per_share(
            nav_before - management + state.performance_fee_accrued, state.units, fx_rate, nav_decimals
        )
        owed = performance_fee_accrual(gross, state.high_water_mark, state.units, share_class.performance_fee)
        accrued = round_money(owed / fx_rate)
        change = round_money(accrued - state.performance_fee_accrued)

    nav = round_money(nav_before - management - change)
    return ClassValuation(
        code=share_class.code,
        nav_before_fees=nav_before,
        management_fee=management,
        performance_fee_accrued=accrued,
        performance_fee_change=change,
        nav=nav,
        nav_per_share=nav_per_share(nav, state.units, fx_rate, nav_decimals),
    )
