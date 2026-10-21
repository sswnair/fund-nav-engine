"""Rounding helpers."""

import pytest

from fundnav.money import round_down, round_half_up, round_money


def test_halves_round_up():
    assert round(2.675, 2) == 2.67  # Python's own round works on the binary value
    assert round_money(2.675) == 2.68


def test_negative_halves_round_away_from_zero():
    assert round_money(-2.675) == -2.68


def test_other_places():
    assert round_half_up(2.00005, 4) == 2.0001
    assert round_half_up(1234.5, 0) == 1235.0


def test_round_down_cuts_toward_zero():
    assert round_down(9.9999, 2) == 9.99
    assert round_down(-1.239, 2) == -1.23
    assert round_down(666.6666, 3) == 666.666


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_numbers_raise(bad):
    with pytest.raises(ValueError):
        round_money(bad)
