"""Positions and cash against the custodian."""

import pandas as pd

from fundnav.models import BREAK_COLUMNS
from fundnav.reconcile import reconcile_cash, reconcile_positions


def test_matching_positions():
    out = reconcile_positions({"A": 100.0, "B": 50.0}, {"A": 100.0, "B": 50.0})
    assert out.empty
    assert list(out.columns) == BREAK_COLUMNS


def test_quantity_break():
    out = reconcile_positions({"A": 100.0}, {"A": 90.0})
    assert out.to_dict("records") == [
        {"key": "POSITION|A", "category": "position", "reference": "A", "detail": "quantity",
         "book": 100.0, "external": 90.0, "difference": 10.0}
    ]


def test_missing_at_custodian():
    row = reconcile_positions({"A": 100.0}, {}).iloc[0]
    assert row["detail"] == "missing at custodian"
    assert row["external"] == 0.0
    assert row["difference"] == 100.0


def test_missing_in_books():
    row = reconcile_positions({}, {"B": 5.0}).iloc[0]
    assert row["detail"] == "missing in books"
    assert row["difference"] == -5.0


def test_zero_and_missing_are_the_same():
    assert reconcile_positions({"A": 0.0}, {}).empty


def test_positions_sorted_by_key():
    out = reconcile_positions({"C": 1.0, "A": 1.0}, {"B": 1.0})
    assert list(out["key"]) == ["POSITION|A", "POSITION|B", "POSITION|C"]


def test_cash_within_tolerance():
    assert reconcile_cash({"EUR": 1000.00}, {"EUR": 995.00}, tolerance=5.0).empty


def test_cash_break():
    out = reconcile_cash({"EUR": 1000.00}, {"EUR": 994.99}, tolerance=5.0)
    assert out.to_dict("records") == [
        {"key": "CASH|EUR", "category": "cash", "reference": "EUR", "detail": "balance",
         "book": 1000.00, "external": 994.99, "difference": 5.01}
    ]


def test_cash_on_one_side_only():
    out = reconcile_cash({"USD": 10.00}, {"GBP": 0.0}, tolerance=5.0)
    assert list(out["key"]) == ["CASH|USD"]
    assert out.loc[0, "difference"] == 10.00


def test_cash_difference_is_in_cents():
    out = reconcile_cash({"EUR": 100.0}, {"EUR": 94.123}, tolerance=5.0)
    assert out.loc[0, "difference"] == 5.88


def test_cash_sorted_by_key():
    out = reconcile_cash({"USD": 50.0, "CHF": 50.0}, {}, tolerance=5.0)
    assert list(out["key"]) == ["CASH|CHF", "CASH|USD"]
    assert isinstance(out, pd.DataFrame)
