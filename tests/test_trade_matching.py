"""Trades against broker confirmations."""

import datetime as dt
import math

import pandas as pd

from fundnav.models import BREAK_COLUMNS, Tolerances
from fundnav.reconcile import match_trades

TOL = Tolerances(cash=5.0, price=0.0001, amount=1.0)
SETTLE = dt.date(2025, 10, 8)


def trades(*rows):
    return pd.DataFrame(rows, columns=["trade_id", "settle_date", "isin", "side", "quantity", "price", "net_amount"])


def confirms(*rows):
    return pd.DataFrame(rows, columns=["confirm_id", "client_ref", "settle_date", "isin", "side", "quantity", "price", "net_amount"])


BOOK = ("T1", SETTLE, "XX1", "BUY", 1000.0, 50.00, 50_025.00)


def test_matching_trade():
    out = match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "BUY", 1000.0, 50.00, 50_025.00)), TOL)
    assert out.empty
    assert list(out.columns) == BREAK_COLUMNS


def test_trade_without_a_confirm():
    row = match_trades(trades(BOOK), confirms(), TOL).iloc[0]
    assert row["key"] == "TRADE|T1"
    assert row["category"] == "trade"
    assert row["detail"] == "no confirm"
    assert row["book"] == 50_025.00
    assert math.isnan(row["external"])


def test_confirm_without_a_trade():
    out = match_trades(trades(), confirms(("C9", "T999", SETTLE, "XX1", "BUY", 10.0, 5.0, 50.0)), TOL)
    assert out.loc[0, "key"] == "CONFIRM|C9"
    assert out.loc[0, "reference"] == "C9"
    assert out.loc[0, "detail"] == "no trade"
    assert out.loc[0, "external"] == 50.0


def test_price_outside_tolerance():
    out = match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "BUY", 1000.0, 50.03, 50_055.00)), TOL)
    assert out.loc[0, "detail"] == "price, net amount"
    assert out.loc[0, "difference"] == -30.00  # book minus confirm


def test_price_inside_tolerance():
    # 50.0025 is half a basis point away, and the net amount is within 1.00
    assert match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "BUY", 1000.0, 50.0025, 50_025.50)), TOL).empty


def test_price_alone():
    book = ("T2", SETTLE, "XX1", "BUY", 10.0, 50.00, 500.00)
    out = match_trades(trades(book), confirms(("C2", "T2", SETTLE, "XX1", "BUY", 10.0, 50.01, 500.10)), TOL)
    assert out.loc[0, "detail"] == "price"


def test_quantity():
    out = match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "BUY", 1100.0, 50.00, 55_027.50)), TOL)
    assert out.loc[0, "detail"] == "quantity, net amount"


def test_settlement_date():
    later = SETTLE + dt.timedelta(days=1)
    out = match_trades(trades(BOOK), confirms(("C1", "T1", later, "XX1", "BUY", 1000.0, 50.00, 50_025.00)), TOL)
    assert out.loc[0, "detail"] == "settlement date"


def test_net_amount_alone():
    out = match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "BUY", 1000.0, 50.00, 50_070.00)), TOL)
    assert out.loc[0, "detail"] == "net amount"
    assert out.loc[0, "difference"] == -45.00


def test_fields_are_listed_in_order():
    later = SETTLE + dt.timedelta(days=1)
    out = match_trades(trades(BOOK), confirms(("C1", "T1", later, "XX2", "SELL", 900.0, 51.00, 45_877.05)), TOL)
    assert out.loc[0, "detail"] == "side, isin, quantity, price, settlement date, net amount"


def test_side_is_compared_without_case():
    assert match_trades(trades(BOOK), confirms(("C1", "T1", SETTLE, "XX1", "buy", 1000.0, 50.00, 50_025.00)), TOL).empty


def test_rows_sorted_by_key():
    out = match_trades(
        trades(("T2", SETTLE, "XX1", "BUY", 1.0, 1.0, 1.0), ("T1", SETTLE, "XX1", "BUY", 1.0, 1.0, 1.0)),
        confirms(("C5", "T7", SETTLE, "XX1", "BUY", 1.0, 1.0, 1.0)),
        TOL,
    )
    assert list(out["key"]) == ["CONFIRM|C5", "TRADE|T1", "TRADE|T2"]
