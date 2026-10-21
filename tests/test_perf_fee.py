"""Performance fees with a high-water mark."""

import pytest

from fundnav.perf_fee import crystallize, crystallize_on_redemption, performance_fee_accrual


@pytest.mark.parametrize("nav_per_share", [119.00, 120.00])
def test_nothing_owed_at_or_below_the_mark(nav_per_share):
    assert performance_fee_accrual(nav_per_share, 120.00, 10_000, 0.10) == 0.0


def test_fee_on_the_gain_above_the_mark():
    assert performance_fee_accrual(132.50, 120.00, 10_000, 0.10) == 12_500.00  # 10% x 12.50 x 10,000


def test_fee_rounds_to_cents():
    assert performance_fee_accrual(120.0003, 120.00, 12_345.678, 0.20) == 0.74


def test_zero_rate():
    assert performance_fee_accrual(150.00, 120.00, 10_000, 0.0) == 0.0


@pytest.mark.parametrize("rate, units", [(-0.1, 10_000), (1.5, 10_000), (0.1, -1)])
def test_bad_inputs(rate, units):
    with pytest.raises(ValueError):
        performance_fee_accrual(130.00, 120.00, units, rate)


def test_crystallizing_pays_the_fee_and_moves_the_mark():
    assert crystallize(12_500.00, 131.25, 120.00) == (12_500.00, 131.25)


def test_nothing_to_crystallize():
    assert crystallize(0.0, 118.00, 120.00) == (0.0, 120.00)


def test_the_mark_never_moves_down():
    assert crystallize(500.00, 119.00, 120.00) == (500.00, 120.00)


def test_negative_accrual_raises():
    with pytest.raises(ValueError):
        crystallize(-1.00, 130.00, 120.00)


def test_redeemed_units_take_their_share():
    assert crystallize_on_redemption(12_500.00, 2_500, 10_000) == 3_125.00


def test_redemption_share_rounds_to_cents():
    assert crystallize_on_redemption(1_000.00, 1, 3) == 333.33


def test_redeeming_everything_and_nothing():
    assert crystallize_on_redemption(500.00, 10, 10) == 500.00
    assert crystallize_on_redemption(500.00, 0, 10) == 0.0


@pytest.mark.parametrize("redeemed, in_issue", [(1, 0), (11, 10), (-1, 10)])
def test_bad_redemption_inputs(redeemed, in_issue):
    with pytest.raises(ValueError):
        crystallize_on_redemption(500.00, redeemed, in_issue)
