"""Splitting the fund's result between share classes, and NAV per share."""

import random

import pytest

from fundnav.classes import allocate, class_weights, nav_per_share
from fundnav.money import round_money


def test_weights():
    assert class_weights({"A": 60.0, "B": 30.0, "C": 10.0}) == pytest.approx({"A": 0.6, "B": 0.3, "C": 0.1})


@pytest.mark.parametrize("navs", [{"A": 0.0, "B": 0.0}, {"A": -1.0, "B": 5.0}])
def test_weights_need_positive_navs(navs):
    with pytest.raises(ValueError):
        class_weights(navs)


def test_pro_rata():
    assert allocate(1000.00, {"A": 0.6, "B": 0.3, "C": 0.1}) == {"A": 600.00, "B": 300.00, "C": 100.00}


def test_rounding_goes_to_the_first_of_tied_classes():
    assert allocate(100.00, {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}) == {"A": 33.34, "B": 33.33, "C": 33.33}


def test_rounding_goes_to_the_largest_class():
    # 0.17 + 0.67 + 0.17 would be 1.01, so the largest class gives back a cent
    assert allocate(1.00, {"A": 1 / 6, "B": 2 / 3, "C": 1 / 6}) == {"A": 0.17, "B": 0.66, "C": 0.17}


def test_losses_split_the_same_way():
    assert allocate(-1000.00, {"A": 0.6, "B": 0.4}) == {"A": -600.00, "B": -400.00}


def test_amount_is_rounded_to_cents_first():
    assert allocate(10.004, {"A": 1.0}) == {"A": 10.00}


def test_parts_always_add_up():
    rng = random.Random(42)
    for _ in range(500):
        raw = [rng.random() for _ in range(rng.randint(2, 5))]
        weights = {f"C{i}": w / sum(raw) for i, w in enumerate(raw)}
        amount = rng.uniform(-1e7, 1e7)
        parts = allocate(amount, weights)
        assert round_money(sum(parts.values())) == round_money(amount)
        assert all(round_money(v) == v for v in parts.values())


def test_nav_per_share():
    assert nav_per_share(1_000_000.00, 8000.0) == 125.0


def test_nav_per_share_in_class_currency():
    assert nav_per_share(1_000_000.00, 8000.0, fx_rate=1.17) == 146.25


def test_nav_per_share_rounds_halves_up():
    assert nav_per_share(2.00005, 1.0) == 2.0001  # round(2.00005, 4) gives 2.0


def test_nav_per_share_decimals():
    assert nav_per_share(1000.00, 3.0, decimals=2) == 333.33


@pytest.mark.parametrize("units", [0.0, -5.0])
def test_nav_per_share_needs_units(units):
    with pytest.raises(ValueError):
        nav_per_share(1000.00, units)
