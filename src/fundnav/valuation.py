"""Valuing positions and cash in the fund's base currency.

FX rates follow the ECB convention: units of a currency per one unit of the
base currency. With EUR as base and EURUSD at 1.17, USD 117.00 is EUR 100.00,
so converting to base means dividing by the rate.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from .money import round_money

POSITION_COLUMNS = ["isin", "quantity", "currency", "price", "local_value", "fx_rate", "base_value"]


def fx_rate(rates: Mapping[str, float], currency: str, base: str) -> float:
    """Units of `currency` per one unit of `base`. The base currency itself is 1.0.

    Raises KeyError when the rate is missing and ValueError when it is zero or
    negative.
    """
    if currency == base:
        return 1.0
    if currency not in rates:
        raise KeyError(f"no FX rate for {currency}")
    rate = float(rates[currency])
    if not rate > 0:
        raise ValueError(f"FX rate for {currency} must be positive, got {rate}")
    return rate


def to_base(amount: float, currency: str, rates: Mapping[str, float], base: str) -> float:
    """An amount in `currency` converted to base currency and rounded to cents."""
    return round_money(amount / fx_rate(rates, currency, base))


def value_positions(
    positions: Mapping[str, float],
    prices: Mapping[str, float],
    currencies: Mapping[str, str],
    rates: Mapping[str, float],
    base: str,
) -> pd.DataFrame:
    """Market value of each holding, in local and base currency.

    Returns one row per ISIN with a non-zero quantity, sorted by ISIN, with the
    columns in POSITION_COLUMNS. local_value is quantity * price rounded to
    cents, and base_value is local_value converted with to_base.

    Raises KeyError naming the ISIN when a holding has no price or no currency.
    """
    rows = []
    for isin in sorted(positions):
        quantity = float(positions[isin])
        if quantity == 0:
            continue
        if isin not in prices:
            raise KeyError(f"no price for {isin}")
        if isin not in currencies:
            raise KeyError(f"no currency for {isin}")
        currency = currencies[isin]
        price = float(prices[isin])
        local = round_money(quantity * price)
        rate = fx_rate(rates, currency, base)
        rows.append([isin, quantity, currency, price, local, rate, round_money(local / rate)])
    return pd.DataFrame(rows, columns=POSITION_COLUMNS)


def value_cash(balances: Mapping[str, float], rates: Mapping[str, float], base: str) -> dict[str, float]:
    """Each currency balance in base currency, rounded to cents, keyed by currency."""
    return {currency: to_base(amount, currency, rates, base) for currency, amount in balances.items()}
