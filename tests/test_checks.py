"""Day-end checks."""

import datetime as dt

import pytest

from fundnav.checks import fx_checks, nav_checks, price_checks

DAY = dt.date(2025, 11, 20)


def test_large_price_move():
    out = price_checks(DAY, ["A"], [{"A": 100.0}, {"A": 85.0}])
    assert [f["check"] for f in out] == ["large price move"]
    assert out[0]["value"] == pytest.approx(-0.15)


def test_stale_price_after_three_unchanged_days():
    history = [{"A": 10.0}, {"A": 11.0}, {"A": 11.0}, {"A": 11.0}]
    assert price_checks(DAY, ["A"], history) == []
    history.append({"A": 11.0})
    assert [f["detail"] for f in price_checks(DAY, ["A"], history)] == ["unchanged for 3 days"]


def test_only_held_securities_are_checked():
    assert price_checks(DAY, [], [{"A": 100.0}, {"A": 50.0}]) == []


def test_fx_move():
    assert [f["reference"] for f in fx_checks(DAY, {"USD": 1.20, "GBP": 0.87}, {"USD": 1.17, "GBP": 0.87})] == ["USD"]


def test_nav_move():
    assert [f["reference"] for f in nav_checks(DAY, {"A-EUR": 104.0, "I-EUR": 100.5}, {"A-EUR": 100.0, "I-EUR": 100.0})] == ["A-EUR"]
