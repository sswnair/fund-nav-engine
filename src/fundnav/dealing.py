"""Subscriptions and redemptions at the day's NAV per share.

Dealing is forward priced: orders received before the cut-off deal at the
NAV per share calculated for that day. Units and proceeds are rounded down,
in the fund's favor.
"""

from __future__ import annotations

from .models import Deal
from .money import round_down


def units_for_subscription(amount: float, nav_per_share: float, decimals: int = 3) -> Deal:
    """Units issued for a cash subscription.

    amount / nav_per_share, rounded down to `decimals` places. The fund keeps
    the whole amount, so the investor is never issued more than was paid for.
    Returns Deal(units, amount).

    Raises ValueError when amount or nav_per_share is not positive.
    """
    if amount <= 0:
        raise ValueError(f"subscription amount must be positive, got {amount}")
    if nav_per_share <= 0:
        raise ValueError(f"NAV per share must be positive, got {nav_per_share}")
    return Deal(units=round_down(amount / nav_per_share, decimals), amount=amount)


def proceeds_for_redemption(units: float, nav_per_share: float) -> Deal:
    """Cash paid out for redeemed units.

    units * nav_per_share, rounded down to cents. Returns Deal(units, amount).

    Raises ValueError when units or nav_per_share is not positive.
    """
    if units <= 0:
        raise ValueError(f"units redeemed must be positive, got {units}")
    if nav_per_share <= 0:
        raise ValueError(f"NAV per share must be positive, got {nav_per_share}")
    return Deal(units=units, amount=round_down(units * nav_per_share, 2))
