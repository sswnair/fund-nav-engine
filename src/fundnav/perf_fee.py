"""Performance fees with a high-water mark.

A class pays a share of its gains above the high-water mark: the NAV per
share at the last period end when a fee was paid. The fee is accrued
daily so the NAV always reflects what would be owed if the period ended
that day. It becomes payable (crystallizes) when the period closes, and
earlier for any units redeemed during the period.
"""

from __future__ import annotations

from .money import round_money


def performance_fee_accrual(nav_per_share_gross: float, high_water_mark: float, units: float, rate: float) -> float:
    """The fee owed for the period so far, in class currency.

    rate * (nav_per_share_gross - high_water_mark) * units, rounded to cents,
    and zero when the NAV per share is at or below the high-water mark.
    nav_per_share_gross is the NAV per share before any performance fee.

    Raises ValueError when rate is outside 0 to 1 or units is negative.
    """
    if not 0 <= rate <= 1:
        raise ValueError(f"rate must be between 0 and 1, got {rate}")
    if units < 0:
        raise ValueError(f"units cannot be negative, got {units}")
    gain = nav_per_share_gross - high_water_mark
    if gain <= 0:
        return 0.0
    return round_money(rate * gain * units)


def crystallize_on_redemption(accrued: float, units_redeemed: float, units_in_issue: float) -> float:
    """The part of the accrued fee that becomes payable when units are redeemed
    before the period ends.

    The redeemed units' share of the accrual, accrued * units_redeemed /
    units_in_issue, rounded to cents. Without this, the accrual would be
    recalculated tomorrow on fewer units and the manager's fee on the
    redeemed units would flow back to the investors who stayed.

    units_in_issue is the number of units at the valuation point, before
    the day's dealing. Raises ValueError when units_redeemed is negative or
    more than units_in_issue, or when units_in_issue is not positive.
    """
    if units_in_issue <= 0:
        raise ValueError(f"units in issue must be positive, got {units_in_issue}")
    if not 0 <= units_redeemed <= units_in_issue:
        raise ValueError(f"cannot redeem {units_redeemed} of {units_in_issue} units")
    return round_money(accrued * units_redeemed / units_in_issue)


def crystallize(accrued: float, nav_per_share: float, high_water_mark: float) -> tuple[float, float]:
    """Close the performance period.

    Returns (payable, new_high_water_mark). The accrued fee becomes payable.
    When a fee is paid, the high-water mark moves up to the period-end NAV per
    share (after the fee); when nothing is paid it stays where it was.

    Raises ValueError for a negative accrual.
    """
    if accrued < 0:
        raise ValueError(f"accrued fee cannot be negative, got {accrued}")
    payable = round_money(accrued)
    if payable > 0:
        return payable, max(high_water_mark, nav_per_share)
    return 0.0, high_water_mark
