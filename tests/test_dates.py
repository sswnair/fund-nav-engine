"""Valuation days."""

import datetime as dt

from fundnav.dates import add_valuation_days, is_valuation_day, next_valuation_day, valuation_days

HOLIDAYS = [dt.date(2025, 10, 27), dt.date(2025, 12, 25), dt.date(2025, 12, 26), dt.date(2026, 1, 1)]


def test_weekends_and_holidays_are_closed():
    assert not is_valuation_day(dt.date(2025, 10, 25), HOLIDAYS)  # Saturday
    assert not is_valuation_day(dt.date(2025, 10, 27), HOLIDAYS)  # holiday
    assert is_valuation_day(dt.date(2025, 10, 28), HOLIDAYS)


def test_fourth_quarter_2025():
    days = valuation_days(dt.date(2025, 10, 1), dt.date(2025, 12, 31), HOLIDAYS)
    assert len(days) == 63
    assert days[0] == dt.date(2025, 10, 1)
    assert days[-1] == dt.date(2025, 12, 31)


def test_next_day_skips_the_holiday_weekend():
    assert next_valuation_day(dt.date(2025, 10, 24), HOLIDAYS) == dt.date(2025, 10, 28)
    assert next_valuation_day(dt.date(2025, 12, 31), HOLIDAYS) == dt.date(2026, 1, 2)


def test_settlement_days():
    assert add_valuation_days(dt.date(2025, 10, 23), 2, HOLIDAYS) == dt.date(2025, 10, 28)
    assert add_valuation_days(dt.date(2025, 12, 22), 3, HOLIDAYS) == dt.date(2025, 12, 29)
