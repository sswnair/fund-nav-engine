"""Daily fee accruals on an actual/365 basis."""

import datetime as dt

import pytest

from fundnav.accruals import accrual_days, accrue_fixed, accrue_percentage


def test_one_day():
    assert accrual_days(dt.date(2025, 10, 1), dt.date(2025, 10, 2)) == 1


def test_monday_carries_the_weekend():
    assert accrual_days(dt.date(2025, 10, 3), dt.date(2025, 10, 6)) == 3


def test_holiday_monday():
    assert accrual_days(dt.date(2025, 10, 24), dt.date(2025, 10, 28)) == 4


@pytest.mark.parametrize("current", [dt.date(2025, 10, 2), dt.date(2025, 10, 1)])
def test_days_must_move_forward(current):
    with pytest.raises(ValueError):
        accrual_days(dt.date(2025, 10, 2), current)


def test_percentage_fee():
    assert accrue_percentage(100_000_000.00, 0.015, 1) == 4109.59  # 4,109.589...


def test_percentage_fee_over_three_days():
    assert accrue_percentage(100_000_000.00, 0.015, 3) == 12328.77


def test_percentage_fee_rounds_halves_up():
    assert accrue_percentage(36682.50, 0.01, 1) == 1.01  # exactly 1.005


def test_other_day_counts():
    assert accrue_percentage(1_000_000.00, 0.0365, 1, day_count=360) == 101.39


def test_no_days_no_fee():
    assert accrue_percentage(1_000_000.00, 0.01, 0) == 0.0


def test_fixed_fee():
    assert accrue_fixed(24_000.00, 1) == 65.75
    assert accrue_fixed(24_000.00, 3) == 197.26


@pytest.mark.parametrize(
    "call",
    [
        lambda: accrue_percentage(1_000_000.00, -0.01, 1),
        lambda: accrue_percentage(1_000_000.00, 0.01, -1),
        lambda: accrue_fixed(-24_000.00, 1),
        lambda: accrue_fixed(24_000.00, -1),
    ],
)
def test_negative_inputs_raise(call):
    with pytest.raises(ValueError):
        call()
