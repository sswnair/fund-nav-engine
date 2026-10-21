"""Day-end checks a reviewer looks at before a NAV goes out.

None of these stops the run. Each one returns findings for someone to look
at: a price that has not moved in days, a large one-day move, an FX rate
that jumped, or a NAV per share that moved more than expected.
"""

from __future__ import annotations

import datetime as dt
from typing import Mapping

STALE_DAYS = 3  # unchanged for this many valuation days in a row
PRICE_MOVE = 0.10  # one-day price move worth a second look
FX_MOVE = 0.02
NAV_MOVE = 0.03


def _finding(day, check, reference, detail, value) -> dict:
    return {"date": day, "check": check, "reference": reference, "detail": detail, "value": value}


def price_checks(
    day: dt.date,
    held: list[str],
    history: list[Mapping[str, float]],
) -> list[dict]:
    """Stale prices and large moves for the securities held.

    history is the price map for each valuation day so far, oldest first,
    ending with `day`.
    """
    findings = []
    if len(history) < 2:
        return findings
    today, yesterday = history[-1], history[-2]
    for isin in held:
        if isin not in today or isin not in yesterday:
            continue
        price, before = today[isin], yesterday[isin]
        if before and abs(price / before - 1) > PRICE_MOVE:
            move = price / before - 1
            findings.append(_finding(day, "large price move", isin, f"{move:+.1%} on the day", move))
        unchanged = 0
        for earlier, later in zip(reversed(history[:-1]), reversed(history)):
            if isin in earlier and isin in later and earlier[isin] == later[isin]:
                unchanged += 1
            else:
                break
        if unchanged >= STALE_DAYS:
            findings.append(_finding(day, "stale price", isin, f"unchanged for {unchanged} days", float(unchanged)))
    return findings


def fx_checks(day: dt.date, today: Mapping[str, float], yesterday: Mapping[str, float]) -> list[dict]:
    findings = []
    for currency, rate in today.items():
        before = yesterday.get(currency)
        if before and abs(rate / before - 1) > FX_MOVE:
            move = rate / before - 1
            findings.append(_finding(day, "large FX move", currency, f"{move:+.1%} on the day", move))
    return findings


def nav_checks(day: dt.date, today: Mapping[str, float], yesterday: Mapping[str, float]) -> list[dict]:
    """NAV per share moves larger than NAV_MOVE, by share class."""
    findings = []
    for code, nps in today.items():
        before = yesterday.get(code)
        if before and abs(nps / before - 1) > NAV_MOVE:
            move = nps / before - 1
            findings.append(_finding(day, "NAV per share move", code, f"{move:+.2%} on the day", move))
    return findings
