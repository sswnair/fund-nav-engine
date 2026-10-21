"""One share class valued for one day."""

import pytest

from fundnav.classes import value_class
from fundnav.models import ClassState, ShareClass

RETAIL = ShareClass("A-EUR", "EUR", management_fee=0.015)
INSTITUTIONAL = ShareClass("I-EUR", "EUR", management_fee=0.0075, performance_fee=0.10)
DOLLAR = ShareClass("I-USD", "USD", management_fee=0.0075, performance_fee=0.10)


def test_class_without_a_performance_fee():
    v = value_class(RETAIL, ClassState("A-EUR", units=100_000, nav=10_000_000.00), allocation=50_000.00, days=1)
    assert v.code == "A-EUR"
    assert v.nav_before_fees == 10_050_000.00
    assert v.management_fee == 413.01  # 10,050,000 x 1.5% / 365
    assert v.performance_fee_accrued == 0.0
    assert v.performance_fee_change == 0.0
    assert v.nav == 10_049_586.99
    assert v.nav_per_share == 100.4959


def test_weekend_fees():
    v = value_class(RETAIL, ClassState("A-EUR", units=100_000, nav=10_000_000.00), allocation=50_000.00, days=3)
    assert v.management_fee == 1239.04
    assert v.nav_per_share == 100.4876


# A class at 128.00 a share, net of a fee already accrued on gains above 120.00.
# Before that fee it was worth 128.8889 a share: 10% of (128.8889 - 120) x 50,000 = 44,444.44.
ABOVE_THE_MARK = ClassState("I-EUR", units=50_000, nav=6_400_000.00, high_water_mark=120.00, performance_fee_accrued=44_444.44)


def test_performance_fee_is_recalculated_on_the_gross_nav():
    v = value_class(INSTITUTIONAL, ABOVE_THE_MARK, allocation=20_000.00, days=1)
    assert v.nav_before_fees == 6_420_000.00
    assert v.management_fee == 131.92
    # gross per share: (6,420,000 - 131.92 + 44,444.44) / 50,000 = 129.2863
    assert v.performance_fee_accrued == 46_431.50  # 10% x 9.2863 x 50,000
    assert v.performance_fee_change == 1_987.06  # only today's increase hits the NAV
    assert v.nav == 6_417_881.02
    assert v.nav_per_share == 128.3576


def test_accrual_reverses_when_the_class_falls_below_the_mark():
    v = value_class(INSTITUTIONAL, ABOVE_THE_MARK, allocation=-500_000.00, days=1)
    assert v.performance_fee_accrued == 0.0
    assert v.performance_fee_change == -44_444.44  # written back to the class
    assert v.nav == 5_944_323.21
    assert v.nav_per_share == 118.8865


def test_class_in_another_currency():
    state = ClassState("I-USD", units=20_000, nav=2_500_000.00, high_water_mark=140.00)
    v = value_class(DOLLAR, state, allocation=0.0, days=1, fx_rate=1.20)
    assert v.management_fee == 51.37  # charged in base currency
    # gross per share in USD: (2,500,000 - 51.37) x 1.20 / 20,000 = 149.9969
    # fee in USD: 10% x 9.9969 x 20,000 = 19,993.80, which is EUR 16,661.50 at 1.20
    assert v.performance_fee_accrued == 16_661.50
    assert v.nav == 2_483_287.13
    assert v.nav_per_share == 148.9972  # in USD


def test_input_state_is_not_changed():
    state = ClassState("A-EUR", units=100_000, nav=10_000_000.00)
    value_class(RETAIL, state, allocation=50_000.00, days=1)
    assert state.nav == 10_000_000.00
    assert state.units == 100_000


def test_amounts_are_in_cents():
    v = value_class(RETAIL, ClassState("A-EUR", units=7, nav=1_000.003), allocation=0.004, days=1)
    for amount in (v.nav_before_fees, v.management_fee, v.nav):
        assert amount == pytest.approx(round(amount, 2), abs=1e-9)
