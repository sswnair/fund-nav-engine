"""Break aging: how long each difference has been open.

The register carries every break from day to day. A break keeps the date
it was first seen until it clears, and its age is counted in the fund's
business days, so a break raised on a Friday is one day old on Monday.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import numpy as np
import pandas as pd

from .models import REGISTER_COLUMNS


def business_days(start: dt.date, end: dt.date, holidays: Iterable[dt.date] = ()) -> int:
    """Business days from start to end: 0 on the same day, 1 on the next
    business day. Weekends and the given holidays are skipped.

    Raises ValueError when end is before start.
    """
    if end < start:
        raise ValueError(f"{end} is before {start}")
    return int(np.busday_count(start, end, holidays=[np.datetime64(h) for h in holidays]))


def age_bucket(age: int) -> str:
    """The aging bucket for an age in business days: "0-1", "2-5", "6-10" or "over 10".

    Raises ValueError for a negative age.
    """
    if age < 0:
        raise ValueError(f"age cannot be negative, got {age}")
    if age <= 1:
        return "0-1"
    if age <= 5:
        return "2-5"
    if age <= 10:
        return "6-10"
    return "over 10"


def update_register(
    register: pd.DataFrame,
    breaks: pd.DataFrame,
    today: dt.date,
    holidays: Iterable[dt.date] = (),
) -> pd.DataFrame:
    """Carry the break register forward to `today`.

    register has the columns in REGISTER_COLUMNS and may be empty; breaks is
    the day's list with the columns in BREAK_COLUMNS. An open break that is
    found again keeps its first_seen date, takes today's detail and
    difference, and has its age and bucket recalculated. A break with no
    open row starts one, aged 0, including a key that was resolved before
    and has come back. An open break that is not found today is marked
    resolved, with resolved_on set to today and the rest of its row
    unchanged. Rows already resolved stay as they are.

    Returns a new frame with the columns in REGISTER_COLUMNS, open rows
    before resolved ones, each sorted by first_seen and then key. The input
    is not changed.
    """
    holidays = list(holidays)
    rows = [] if register.empty else register.to_dict("records")
    open_rows = {r["key"]: r for r in rows if r["status"] == "open"}
    today_rows = {b["key"]: b for b in breaks.to_dict("records")}

    for key, row in open_rows.items():
        if key in today_rows:
            b = today_rows[key]
            row["last_seen"] = today
            row["detail"] = b["detail"]
            row["difference"] = b["difference"]
            row["age"] = business_days(row["first_seen"], today, holidays)
            row["bucket"] = age_bucket(row["age"])
        else:
            row["status"] = "resolved"
            row["resolved_on"] = today

    for key, b in today_rows.items():
        if key in open_rows:
            continue
        rows.append(
            {
                "key": key,
                "category": b["category"],
                "reference": b["reference"],
                "detail": b["detail"],
                "difference": b["difference"],
                "first_seen": today,
                "last_seen": today,
                "age": 0,
                "bucket": age_bucket(0),
                "status": "open",
                "resolved_on": None,
            }
        )

    out = pd.DataFrame(rows, columns=REGISTER_COLUMNS)
    if out.empty:
        return out
    out["_order"] = (out["status"] != "open").astype(int)
    out = out.sort_values(["_order", "first_seen", "key"]).drop(columns="_order").reset_index(drop=True)
    return out
