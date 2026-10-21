"""Business-day ages and the break register."""

import datetime as dt

import pandas as pd
import pytest

from fundnav.aging import age_bucket, business_days, update_register
from fundnav.models import BREAK_COLUMNS, REGISTER_COLUMNS

FRI, MON, TUE = dt.date(2025, 10, 24), dt.date(2025, 10, 27), dt.date(2025, 10, 28)
HOLIDAY = [MON]


def breaks(*rows):
    return pd.DataFrame(rows, columns=BREAK_COLUMNS)


def cash_break(difference):
    return ("CASH|EUR", "cash", "EUR", "balance", 1000.0, 1000.0 - difference, difference)


EMPTY = pd.DataFrame(columns=REGISTER_COLUMNS)


def test_same_day_is_zero():
    assert business_days(FRI, FRI) == 0


def test_weekend_is_skipped():
    assert business_days(FRI, MON) == 1


def test_holiday_is_skipped():
    assert business_days(FRI, TUE, HOLIDAY) == 1
    assert business_days(FRI, TUE) == 2


def test_end_before_start_raises():
    with pytest.raises(ValueError):
        business_days(TUE, FRI)


@pytest.mark.parametrize("age, bucket", [(0, "0-1"), (1, "0-1"), (2, "2-5"), (5, "2-5"), (6, "6-10"), (10, "6-10"), (11, "over 10"), (40, "over 10")])
def test_buckets(age, bucket):
    assert age_bucket(age) == bucket


def test_negative_age_raises():
    with pytest.raises(ValueError):
        age_bucket(-1)


def test_new_break_opens_a_row():
    out = update_register(EMPTY, breaks(cash_break(37.5)), FRI)
    assert list(out.columns) == REGISTER_COLUMNS
    row = out.iloc[0]
    assert (row["key"], row["first_seen"], row["last_seen"], row["age"], row["bucket"], row["status"]) == (
        "CASH|EUR", FRI, FRI, 0, "0-1", "open"
    )


def test_open_break_ages():
    day1 = update_register(EMPTY, breaks(cash_break(37.5)), FRI, HOLIDAY)
    day2 = update_register(day1, breaks(cash_break(40.0)), TUE, HOLIDAY)
    row = day2.iloc[0]
    assert len(day2) == 1
    assert row["first_seen"] == FRI
    assert row["last_seen"] == TUE
    assert row["age"] == 1  # Monday was a holiday
    assert row["difference"] == 40.0  # today's figure


def test_break_that_clears_is_resolved():
    day1 = update_register(EMPTY, breaks(cash_break(37.5)), FRI)
    day2 = update_register(day1, breaks(), MON)
    row = day2.iloc[0]
    assert row["status"] == "resolved"
    assert row["resolved_on"] == MON
    assert row["age"] == 0
    assert row["last_seen"] == FRI


def test_break_that_comes_back_is_new():
    day1 = update_register(EMPTY, breaks(cash_break(37.5)), FRI)
    day2 = update_register(day1, breaks(), MON)
    day3 = update_register(day2, breaks(cash_break(12.0)), TUE)
    assert len(day3) == 2
    assert list(day3["status"]) == ["open", "resolved"]
    assert day3.iloc[0]["first_seen"] == TUE


def test_open_rows_come_first():
    day1 = update_register(EMPTY, breaks(cash_break(1.0), ("TRADE|T1", "trade", "T1", "no confirm", 5.0, None, None)), FRI)
    day2 = update_register(day1, breaks(("TRADE|T1", "trade", "T1", "no confirm", 5.0, None, None),
                                        ("POSITION|A", "position", "A", "quantity", 10.0, 9.0, 1.0)), MON)
    assert list(day2["key"]) == ["TRADE|T1", "POSITION|A", "CASH|EUR"]
    assert list(day2["status"]) == ["open", "open", "resolved"]


def test_input_is_not_changed():
    day1 = update_register(EMPTY, breaks(cash_break(37.5)), FRI)
    before = day1.copy()
    update_register(day1, breaks(), MON)
    pd.testing.assert_frame_equal(day1, before)
