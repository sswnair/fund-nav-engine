"""Daily fee accruals.

Fees accrue every calendar day, not only on valuation days, on an
actual/365 basis. A Monday NAV carries three days of fees: Saturday, Sunday
and Monday. A Tuesday after a Monday holiday carries four.
"""

from __future__ import annotations

import datetime as dt

from .money import round_money


def accrual_days(previous: dt.date, current: dt.date) -> int:
    """Calendar days from the previous valuation day to this one.

    Raises ValueError unless current is after previous.
    """
    days = (current - previous).days
    if days <= 0:
        raise ValueError(f"{current} is not after {previous}")
    return days


def accrue_percentage(base_amount: float, annual_rate: float, days: int, day_count: int = 365) -> float:
    """A fee charged as a yearly percentage: base_amount * annual_rate * days / day_count,
    rounded to cents.

    Raises ValueError for a negative rate or negative days.
    """
    if annual_rate < 0:
        raise ValueError(f"annual_rate cannot be negative, got {annual_rate}")
    if days < 0:
        raise ValueError(f"days cannot be negative, got {days}")
    return round_money(base_amount * annual_rate * days / day_count)


def accrue_fixed(annual_amount: float, days: int, day_count: int = 365) -> float:
    """A fixed yearly fee spread evenly over the days: annual_amount * days / day_count,
    rounded to cents.

    Raises ValueError for a negative amount or negative days.
    """
    if annual_amount < 0:
        raise ValueError(f"annual_amount cannot be negative, got {annual_amount}")
    if days < 0:
        raise ValueError(f"days cannot be negative, got {days}")
    return round_money(annual_amount * days / day_count)
