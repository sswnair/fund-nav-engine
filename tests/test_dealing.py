"""Subscriptions and redemptions at the day's NAV per share."""

import pytest

from fundnav.dealing import proceeds_for_redemption, units_for_subscription
from fundnav.models import Deal


def test_subscription_units():
    assert units_for_subscription(100_000.00, 128.3576) == Deal(units=779.073, amount=100_000.00)


def test_units_are_never_rounded_up():
    assert units_for_subscription(2_000.00, 3.0).units == 666.666  # not 666.667


def test_exact_units():
    assert units_for_subscription(1_000.00, 125.0) == Deal(units=8.0, amount=1_000.00)


def test_unit_decimals():
    assert units_for_subscription(2_000.00, 3.0, decimals=2).units == 666.66


@pytest.mark.parametrize("amount, nav_per_share", [(0.0, 100.0), (-5.0, 100.0), (100.0, 0.0)])
def test_bad_subscriptions(amount, nav_per_share):
    with pytest.raises(ValueError):
        units_for_subscription(amount, nav_per_share)


def test_redemption_proceeds():
    assert proceeds_for_redemption(1_250.0, 116.8434) == Deal(units=1_250.0, amount=146_054.25)


def test_proceeds_are_rounded_down():
    assert proceeds_for_redemption(1.001, 99.999).amount == 100.09  # 100.097999, not 100.10
    assert proceeds_for_redemption(3.333, 100.0).amount == 333.30


@pytest.mark.parametrize("units, nav_per_share", [(0.0, 100.0), (-1.0, 100.0), (10.0, 0.0)])
def test_bad_redemptions(units, nav_per_share):
    with pytest.raises(ValueError):
        proceeds_for_redemption(units, nav_per_share)
