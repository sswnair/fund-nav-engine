"""Rounding for money, prices and units.

Arithmetic happens in floats, which is precise enough at these sizes, but
every amount that gets posted is rounded first. Python's round() rounds
halves to even and works on the binary value, so round(2.675, 2) gives 2.67.
These helpers go through Decimal and round halves away from zero instead,
the usual convention in fund accounts.
"""

from __future__ import annotations

import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


def _quantize(value: float, places: int, mode: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"cannot round {value}")
    step = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(value))).quantize(step, rounding=mode))


def round_half_up(value: float, places: int = 2) -> float:
    """Round to `places` decimals, halves away from zero: 2.675 -> 2.68, -2.675 -> -2.68."""
    return _quantize(value, places, ROUND_HALF_UP)


def round_money(value: float) -> float:
    """Round an amount to cents, halves away from zero."""
    return _quantize(value, 2, ROUND_HALF_UP)


def round_down(value: float, places: int = 2) -> float:
    """Cut to `places` decimals, toward zero: 9.9999 -> 9.99."""
    return _quantize(value, places, ROUND_DOWN)
