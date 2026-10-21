"""The books: trade date, settlement date, income and fee payments."""

import datetime as dt

import pytest

from fundnav.ledger import Ledger


def day(n):
    return dt.date(2025, 10, n)


def test_trade_moves_positions_before_cash(sample):
    ledger = Ledger.open(sample)
    t = sample.trades.set_index("trade_id").loc["T0001"]  # Elm, bought on Oct 2, settles Oct 6
    before_traded, before_settled = ledger.traded[t["isin"]], ledger.settled[t["isin"]]
    eur = ledger.cash["EUR"]

    ledger.apply_day(day(1), sample, first_of_month=True)
    paid_fees = eur - ledger.cash["EUR"]
    ledger.apply_day(day(2), sample, first_of_month=False)
    assert ledger.traded[t["isin"]] == before_traded + t["quantity"]
    assert ledger.settled[t["isin"]] == before_settled
    assert ledger.payables["T0001"].amount == t["net_amount"]

    for n in (3, 6):
        ledger.apply_day(day(n), sample, first_of_month=False)
    assert ledger.settled[t["isin"]] == before_settled + t["quantity"]
    assert "T0001" not in ledger.payables
    assert ledger.cash["EUR"] == pytest.approx(eur - paid_fees - t["net_amount"])


def test_fees_accrued_last_month_are_paid_on_the_first_day(sample):
    ledger = Ledger.open(sample)
    owed = sum(sample.opening.expenses_accrued.values()) + sum(sample.opening.management_fees_accrued.values())
    eur = ledger.cash["EUR"]
    ledger.apply_day(day(1), sample, first_of_month=True)
    assert ledger.cash["EUR"] == pytest.approx(eur - owed)
    assert all(v == 0 for v in ledger.expenses_accrued.values())
    assert all(v == 0 for v in ledger.management_fees_accrued.values())


def test_dividend_accrues_on_ex_date_and_pays_on_pay_date(sample):
    ledger = Ledger.open(sample)
    d = sample.dividends.iloc[0]  # Fir Software, ex Oct 15, paid Oct 30
    for n in range(1, 16):
        when = day(n)
        if when.weekday() < 5:
            ledger.apply_day(when, sample, first_of_month=n == 1)
    key = f"DIV|{d['isin']}|{d['ex_date']}"
    held = ledger.traded[d["isin"]]
    assert ledger.receivables[key].amount == pytest.approx(round(held * d["amount_per_share"] * (1 - d["withholding_rate"]), 2))
    assert ledger.receivables[key].due == d["pay_date"]


def test_crystallizing_moves_the_accrual_to_payable(sample):
    ledger = Ledger.open(sample)
    accrued = ledger.performance_fees_accrued["I-EUR"]
    ledger.crystallize("I-EUR", 1000.00)
    assert ledger.performance_fees_accrued["I-EUR"] == pytest.approx(accrued - 1000.00)
    assert ledger.performance_fees_payable["I-EUR"] == 1000.00
