"""Valuing positions and cash in base currency."""

import pytest

from fundnav.valuation import POSITION_COLUMNS, fx_rate, to_base, value_cash, value_positions

RATES = {"USD": 1.17, "GBP": 0.87}


def test_base_currency_rate_is_one():
    assert fx_rate(RATES, "EUR", "EUR") == 1.0


def test_rate_lookup():
    assert fx_rate(RATES, "USD", "EUR") == 1.17


def test_missing_rate_raises():
    with pytest.raises(KeyError):
        fx_rate(RATES, "CHF", "EUR")


@pytest.mark.parametrize("bad", [0.0, -1.17])
def test_rate_must_be_positive(bad):
    with pytest.raises(ValueError):
        fx_rate({"USD": bad}, "USD", "EUR")


def test_converting_divides_by_the_rate():
    assert to_base(117.00, "USD", RATES, "EUR") == 100.00


def test_converting_rounds_to_cents():
    assert to_base(100.00, "USD", RATES, "EUR") == 85.47  # 85.4700854...


def test_converting_rounds_halves_up():
    assert to_base(2.675, "EUR", RATES, "EUR") == 2.68  # round(2.675, 2) gives 2.67


def test_positions():
    frame = value_positions(
        {"XX1": 1000, "XX2": 250, "XX3": 0},
        {"XX1": 12.345, "XX2": 40.0, "XX3": 5.0},
        {"XX1": "EUR", "XX2": "USD", "XX3": "EUR"},
        {"USD": 1.25},
        "EUR",
    )
    assert list(frame.columns) == POSITION_COLUMNS
    assert list(frame["isin"]) == ["XX1", "XX2"]  # nothing for a zero holding
    assert list(frame["local_value"]) == [12345.00, 10000.00]
    assert list(frame["fx_rate"]) == [1.0, 1.25]
    assert list(frame["base_value"]) == [12345.00, 8000.00]


def test_local_value_is_rounded_before_converting():
    frame = value_positions({"XX4": 1}, {"XX4": 2.345}, {"XX4": "GBP"}, {"GBP": 0.5}, "EUR")
    assert frame.loc[0, "local_value"] == 2.35
    assert frame.loc[0, "base_value"] == 4.70  # 2.35 / 0.5, not round(2.345 / 0.5) = 4.69


def test_sorted_by_isin():
    frame = value_positions({"B": 1, "A": 1}, {"A": 1.0, "B": 1.0}, {"A": "EUR", "B": "EUR"}, {}, "EUR")
    assert list(frame["isin"]) == ["A", "B"]


def test_missing_price_names_the_security():
    with pytest.raises(KeyError, match="XX9"):
        value_positions({"XX9": 10}, {}, {"XX9": "EUR"}, {}, "EUR")


def test_missing_fx_rate_raises():
    with pytest.raises(KeyError):
        value_positions({"XX1": 10}, {"XX1": 5.0}, {"XX1": "CHF"}, {}, "EUR")


def test_cash():
    assert value_cash({"EUR": 1000.00, "USD": 1170.00, "GBP": 0.0}, RATES, "EUR") == {
        "EUR": 1000.00,
        "USD": 1000.00,
        "GBP": 0.0,
    }
