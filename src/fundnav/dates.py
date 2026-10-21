"""Valuation days: weekdays that are not fund holidays."""

from __future__ import annotations

import datetime as dt
from typing import Iterable


def is_valuation_day(day: dt.date, holidays: Iterable[dt.date]) -> bool:
    return day.weekday() < 5 and day not in set(holidays)


def valuation_days(start: dt.date, end: dt.date, holidays: Iterable[dt.date]) -> list[dt.date]:
    """Every valuation day from start to end, both included."""
    closed = set(holidays)
    days, day = [], start
    while day <= end:
        if day.weekday() < 5 and day not in closed:
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def next_valuation_day(day: dt.date, holidays: Iterable[dt.date]) -> dt.date:
    closed = set(holidays)
    day += dt.timedelta(days=1)
    while day.weekday() >= 5 or day in closed:
        day += dt.timedelta(days=1)
    return day


def add_valuation_days(day: dt.date, count: int, holidays: Iterable[dt.date]) -> dt.date:
    """The valuation day `count` days after `day`, as used for T+2 or T+3 settlement."""
    for _ in range(count):
        day = next_valuation_day(day, holidays)
    return day
