"""Reconciliation: the fund's books against the custodian and the brokers.

Positions and cash are checked against the custodian's statements on a
settled basis, since that is what a custodian reports. Trades are checked
against the brokers' confirmations. Each function returns one row per
difference, with the columns in models.BREAK_COLUMNS, sorted by key.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from .models import BREAK_COLUMNS, Tolerances
from .money import round_money

QUANTITY_TOLERANCE = 1e-6


def _frame(rows: list[list]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=BREAK_COLUMNS)
    return frame.sort_values("key").reset_index(drop=True)


def reconcile_positions(book: Mapping[str, float], custodian: Mapping[str, float]) -> pd.DataFrame:
    """Settled positions in the books against the custodian's holdings.

    A position missing on one side counts as zero there, and two zeros are
    not a break. Quantities more than QUANTITY_TOLERANCE apart are a break:

        key         "POSITION|<isin>"
        category    "position"
        reference   the ISIN
        detail      "quantity" when both sides hold it, "missing at custodian"
                    when only the books do, "missing in books" when only the
                    custodian does
        book, external, difference   book quantity, custodian quantity,
                    and book minus custodian
    """
    rows = []
    for isin in sorted(set(book) | set(custodian)):
        ours, theirs = float(book.get(isin, 0.0)), float(custodian.get(isin, 0.0))
        if abs(ours - theirs) <= QUANTITY_TOLERANCE:
            continue
        if abs(theirs) <= QUANTITY_TOLERANCE:
            detail = "missing at custodian"
        elif abs(ours) <= QUANTITY_TOLERANCE:
            detail = "missing in books"
        else:
            detail = "quantity"
        rows.append([f"POSITION|{isin}", "position", isin, detail, ours, theirs, ours - theirs])
    return _frame(rows)


def reconcile_cash(book: Mapping[str, float], custodian: Mapping[str, float], tolerance: float) -> pd.DataFrame:
    """Cash balances in the books against the custodian, currency by currency.

    A currency on one side only counts as zero on the other. The difference
    is rounded to cents and is a break when it is larger than `tolerance`
    (in that currency's units):

        key "CASH|<currency>", category "cash", reference the currency,
        detail "balance", book, external (custodian), difference = book minus custodian
    """
    rows = []
    for currency in sorted(set(book) | set(custodian)):
        ours, theirs = float(book.get(currency, 0.0)), float(custodian.get(currency, 0.0))
        difference = round_money(ours - theirs)
        if abs(difference) > tolerance:
            rows.append([f"CASH|{currency}", "cash", currency, "balance", ours, theirs, difference])
    return _frame(rows)


def match_trades(trades: pd.DataFrame, confirms: pd.DataFrame, tolerances: Tolerances) -> pd.DataFrame:
    """The fund's trades against broker confirmations, matched on trade id.

    trades has the columns trade_id, settle_date, isin, side, quantity, price
    and net_amount. confirms has the same fields plus confirm_id and
    client_ref, the fund's trade id as the broker recorded it, with one live
    version per confirmation.

    A trade with no confirmation is keyed "TRADE|<trade_id>" with the detail
    "no confirm", and a confirmation that matches no trade is keyed
    "CONFIRM|<confirm_id>" with the detail "no trade". When a pair disagrees,
    the detail names the fields that differ, in the order side, isin,
    quantity, price, settlement date, net amount, as in "price, net amount".
    Prices differ when they are more than tolerances.price apart relative to
    the book price, net amounts when they are more than tolerances.amount
    apart, and the other fields on any difference. The category is "trade";
    book and external are the two net amounts (NaN on a missing side) and
    difference is book minus external. Pairs that agree produce no row.
    """
    rows = []
    confirms = confirms.copy()
    confirms["client_ref"] = confirms["client_ref"].astype(str)
    by_ref = {ref: row for ref, row in zip(confirms["client_ref"], confirms.itertuples(index=False))}
    trade_ids = set(trades["trade_id"].astype(str))

    for t in trades.itertuples(index=False):
        c = by_ref.get(str(t.trade_id))
        key = f"TRADE|{t.trade_id}"
        if c is None:
            rows.append([key, "trade", t.trade_id, "no confirm", t.net_amount, float("nan"), float("nan")])
            continue
        fields = []
        if str(c.side).upper() != str(t.side).upper():
            fields.append("side")
        if c.isin != t.isin:
            fields.append("isin")
        if abs(c.quantity - t.quantity) > QUANTITY_TOLERANCE:
            fields.append("quantity")
        if abs(c.price - t.price) / t.price > tolerances.price:
            fields.append("price")
        if c.settle_date != t.settle_date:
            fields.append("settlement date")
        if abs(c.net_amount - t.net_amount) > tolerances.amount:
            fields.append("net amount")
        if fields:
            rows.append(
                [key, "trade", t.trade_id, ", ".join(fields), t.net_amount, c.net_amount, round_money(t.net_amount - c.net_amount)]
            )

    for c in confirms.itertuples(index=False):
        if c.client_ref not in trade_ids:
            rows.append([f"CONFIRM|{c.confirm_id}", "trade", c.confirm_id, "no trade", float("nan"), c.net_amount, float("nan")])
    return _frame(rows)
