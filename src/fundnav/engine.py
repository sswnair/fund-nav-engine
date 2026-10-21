"""The daily NAV run.

For each valuation day:

1. Book the day's dividends, trades, settlements and fee payments.
2. Value positions, cash and everything due in or out, in base currency.
3. Accrue the fund's shared expenses.
4. Split the fund's result for the day between the share classes, by their
   NAV at the previous valuation point.
5. Value each class: management fee, performance fee, NAV per share.
6. Deal subscriptions and redemptions at that NAV per share.
7. Crystallize performance fees if this is the last valuation day of the year.
8. Prove the NAV: the balance sheet must equal the sum of the class NAVs.
9. Reconcile against the custodian and brokers, and age the breaks.
"""

from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from .accruals import accrual_days, accrue_fixed, accrue_percentage
from .aging import update_register
from .checks import fx_checks, nav_checks, price_checks
from .classes import allocate, class_weights, nav_per_share, value_class
from .data import FundData
from .dates import add_valuation_days, next_valuation_day, valuation_days
from .dealing import proceeds_for_redemption, units_for_subscription
from .ledger import Ledger
from .models import BREAK_COLUMNS, REGISTER_COLUMNS, ClassState, ClassValuation
from .money import round_money
from .perf_fee import crystallize, crystallize_on_redemption
from .reconcile import match_trades, reconcile_cash, reconcile_positions
from .valuation import fx_rate, to_base, value_cash, value_positions

ASSET_LINES = ["Investments", "Cash", "Sales awaiting settlement", "Dividends receivable", "Subscriptions receivable"]
LIABILITY_LINES = [
    "Purchases awaiting settlement",
    "Redemptions payable",
    "Expenses accrued",
    "Management fees accrued",
    "Performance fees accrued",
    "Performance fees payable",
]


def balance_sheet(ledger: Ledger, positions: pd.DataFrame, rates: dict[str, float]) -> dict[str, float]:
    """The fund's net assets in base currency, line by line. Liabilities are negative."""
    base = ledger.base

    def items(side: str, kind: str) -> float:
        return round_money(sum(to_base(i.amount, i.currency, rates, base) for _, i in ledger.items(side, kind)))

    lines = {
        "Investments": round_money(float(positions["base_value"].sum())) if not positions.empty else 0.0,
        "Cash": round_money(sum(value_cash(ledger.cash, rates, base).values())),
        "Sales awaiting settlement": items("receivable", "sale"),
        "Dividends receivable": items("receivable", "income"),
        "Subscriptions receivable": items("receivable", "subscription"),
        "Purchases awaiting settlement": -items("payable", "purchase"),
        "Redemptions payable": -items("payable", "redemption"),
        "Expenses accrued": -round_money(sum(ledger.expenses_accrued.values())),
        "Management fees accrued": -round_money(sum(ledger.management_fees_accrued.values())),
        "Performance fees accrued": -round_money(sum(ledger.performance_fees_accrued.values())),
        "Performance fees payable": -round_money(sum(ledger.performance_fees_payable.values())),
    }
    lines["Net assets"] = round_money(sum(lines.values()))
    return lines


@dataclass
class DayResult:
    date: dt.date
    accrual_days: int
    rates: dict[str, float]
    positions: pd.DataFrame
    balance_sheet: dict[str, float]
    result: float  # the fund's result before class fees, split between classes
    allocation: dict[str, float]
    expenses: dict[str, float]
    valuations: dict[str, ClassValuation]
    states: dict[str, ClassState]  # after dealing
    deals: list[dict]
    crystallized: dict[str, float]
    proof: float  # balance sheet net assets less the sum of class NAVs
    cash: dict[str, float]  # settled cash by currency, at the end of the day
    settled_positions: dict[str, float]
    breaks: pd.DataFrame
    register: pd.DataFrame
    checks: list[dict]

    @property
    def net_assets(self) -> float:
        return self.balance_sheet["Net assets"]


@dataclass
class RunResult:
    data: FundData
    opening_balance_sheet: dict[str, float]
    opening_states: dict[str, ClassState]
    opening_nav_per_share: dict[str, float]
    days: list[DayResult] = field(default_factory=list)
    events: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def last(self) -> DayResult:
        return self.days[-1]

    def nav_history(self) -> pd.DataFrame:
        rows = []
        for d in self.days:
            for code, v in d.valuations.items():
                s = d.states[code]
                rows.append(
                    {
                        "date": d.date,
                        "share_class": code,
                        "currency": self.data.config.share_class(code).currency,
                        "nav_per_share": v.nav_per_share,
                        "units": s.units,
                        "nav_base": s.nav,
                        "management_fee": v.management_fee,
                        "performance_fee_accrued": v.performance_fee_accrued,
                        "performance_fee_change": v.performance_fee_change,
                        "high_water_mark": s.high_water_mark,
                    }
                )
        return pd.DataFrame(rows)

    def balance_sheets(self) -> pd.DataFrame:
        rows = [{"date": self.data.opening.date, **self.opening_balance_sheet}]
        rows += [{"date": d.date, **d.balance_sheet, "Proof difference": d.proof} for d in self.days]
        return pd.DataFrame(rows)

    def deals(self) -> pd.DataFrame:
        return pd.DataFrame([deal for d in self.days for deal in d.deals])

    def checks(self) -> pd.DataFrame:
        return pd.DataFrame([c for d in self.days for c in d.checks], columns=["date", "check", "reference", "detail", "value"])

    def breaks_by_day(self) -> pd.DataFrame:
        frames = [d.breaks.assign(date=d.date) for d in self.days if not d.breaks.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", *BREAK_COLUMNS])


def reconcile_day(day: dt.date, ledger: Ledger, data: FundData) -> pd.DataFrame:
    tolerances = data.config.tolerances
    frames = []
    custodian_positions = data.custodian_positions_on(day)
    if custodian_positions is not None:
        frames.append(reconcile_positions(ledger.settled, custodian_positions))
    custodian_cash = data.custodian_cash_on(day)
    if custodian_cash is not None:
        frames.append(reconcile_cash(ledger.cash, custodian_cash, tolerances.cash))
    trades = data.booked_trades(day)
    if not trades.empty:
        frames.append(match_trades(trades, data.live_confirms(day), tolerances))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=BREAK_COLUMNS)
    return pd.concat(frames, ignore_index=True).sort_values("key").reset_index(drop=True)


def run(data: FundData, start: dt.date | None = None, end: dt.date | None = None) -> RunResult:
    config = data.config
    base = config.base_currency
    opening = data.opening
    currencies = data.securities["currency"].to_dict()

    ledger = Ledger.open(data)
    states = {code: copy.deepcopy(s) for code, s in opening.share_classes.items()}

    open_rates = data.fx_on(opening.date)
    open_positions = value_positions(ledger.traded, data.prices_on(opening.date), currencies, open_rates, base)
    opening_sheet = balance_sheet(ledger, open_positions, open_rates)
    opening_nps = {
        sc.code: nav_per_share(states[sc.code].nav, states[sc.code].units, fx_rate(open_rates, sc.currency, base), config.nav_decimals)
        for sc in config.share_classes
    }
    result = RunResult(data, opening_sheet, copy.deepcopy(states), opening_nps)

    last_price_day = max(data.prices["date"])
    days = valuation_days(start or next_valuation_day(opening.date, config.holidays), end or last_price_day, config.holidays)
    previous_day = opening.date
    previous_nav = round_money(sum(s.nav for s in states.values()))
    previous_nps = dict(opening_nps)
    previous_rates = open_rates
    price_history = [data.prices_on(opening.date)]
    register = pd.DataFrame(columns=REGISTER_COLUMNS)

    for day in days:
        rates = data.fx_on(day)
        if not rates:
            raise ValueError(f"no FX rates for {day}")
        prices = data.prices_on(day)
        price_history.append(prices)

        # 1. Book the day.
        ledger.apply_day(day, data, first_of_month=day.month != previous_day.month)

        # 2. Value the fund before the day's accruals.
        positions = value_positions(ledger.traded, prices, currencies, rates, base)
        gross = balance_sheet(ledger, positions, rates)["Net assets"]
        days_accrued = accrual_days(previous_day, day)

        # 3. Shared expenses.
        expenses = {}
        for e in config.expenses:
            if e.annual_rate is not None:
                amount = accrue_percentage(gross, e.annual_rate, days_accrued)
            else:
                amount = accrue_fixed(e.annual_amount, days_accrued)
            ledger.post_expense(e.name, amount)
            expenses[e.name] = amount

        # 4. Split the result between classes.
        before_class_fees = round_money(gross - sum(expenses.values()))
        fund_result = round_money(before_class_fees - previous_nav)
        allocation = allocate(fund_result, class_weights({code: s.nav for code, s in states.items()}))

        # 5. Value each class.
        valuations = {}
        for sc in config.share_classes:
            state = states[sc.code]
            v = value_class(sc, state, allocation[sc.code], days_accrued, fx_rate(rates, sc.currency, base), config.nav_decimals)
            ledger.post_management_fee(sc.code, v.management_fee)
            ledger.set_performance_fee(sc.code, v.performance_fee_accrued)
            state.nav = v.nav
            state.performance_fee_accrued = v.performance_fee_accrued
            valuations[sc.code] = v

        # 6. Deal at the day's NAV per share.
        settle = add_valuation_days(day, config.capital_settlement_days, config.holidays)
        units_at_valuation = {code: s.units for code, s in states.items()}
        accrued_at_valuation = {code: s.performance_fee_accrued for code, s in states.items()}
        deals = []
        for d in data.deals[data.deals["deal_date"] == day].itertuples(index=False):
            sc = config.share_class(d.share_class)
            state, v = states[sc.code], valuations[sc.code]
            if d.type == "subscription":
                deal = units_for_subscription(float(d.amount), v.nav_per_share, config.unit_decimals)
                base_amount = to_base(deal.amount, sc.currency, rates, base)
                state.units = round(state.units + deal.units, config.unit_decimals)
                state.nav = round_money(state.nav + base_amount)
                ledger.book_subscription(d.deal_id, sc.currency, deal.amount, settle)
                crystallized_now = 0.0
            else:
                deal = proceeds_for_redemption(float(d.units), v.nav_per_share)
                base_amount = to_base(deal.amount, sc.currency, rates, base)
                crystallized_now = 0.0
                if sc.performance_fee and accrued_at_valuation[sc.code] > 0:
                    crystallized_now = crystallize_on_redemption(
                        accrued_at_valuation[sc.code], deal.units, units_at_valuation[sc.code]
                    )
                    ledger.crystallize(sc.code, crystallized_now)
                    state.performance_fee_accrued = round_money(state.performance_fee_accrued - crystallized_now)
                state.units = round(state.units - deal.units, config.unit_decimals)
                state.nav = round_money(state.nav - base_amount)
                ledger.book_redemption(d.deal_id, sc.currency, deal.amount, settle)
            deals.append(
                {
                    "date": day,
                    "deal_id": d.deal_id,
                    "share_class": sc.code,
                    "type": d.type,
                    "investor": d.investor,
                    "nav_per_share": v.nav_per_share,
                    "units": deal.units,
                    "amount": deal.amount,
                    "currency": sc.currency,
                    "base_amount": base_amount,
                    "settles": settle,
                    "performance_fee_crystallized": crystallized_now,
                }
            )

        # 7. Year end: performance fees become payable.
        crystallized = {}
        if next_valuation_day(day, config.holidays).year != day.year:
            for sc in config.share_classes:
                if not sc.performance_fee:
                    continue
                state = states[sc.code]
                payable, mark = crystallize(state.performance_fee_accrued, valuations[sc.code].nav_per_share, state.high_water_mark)
                ledger.crystallize(sc.code, payable)
                state.performance_fee_accrued = 0.0
                state.high_water_mark = mark
                crystallized[sc.code] = payable

        # 8. NAV proof.
        sheet = balance_sheet(ledger, positions, rates)
        class_total = round_money(sum(s.nav for s in states.values()))
        proof = round_money(sheet["Net assets"] - class_total)

        # 9. Reconcile and age the breaks.
        breaks = reconcile_day(day, ledger, data)
        register = update_register(register, breaks, day, config.holidays)

        nps_today = {code: v.nav_per_share for code, v in valuations.items()}
        held = sorted(ledger.traded)
        checks = (
            price_checks(day, held, price_history)
            + fx_checks(day, rates, previous_rates)
            + nav_checks(day, nps_today, previous_nps)
        )

        result.days.append(
            DayResult(
                date=day,
                accrual_days=days_accrued,
                rates=rates,
                positions=positions,
                balance_sheet=sheet,
                result=fund_result,
                allocation=allocation,
                expenses=expenses,
                valuations=valuations,
                states=copy.deepcopy(states),
                deals=deals,
                crystallized=crystallized,
                proof=proof,
                cash=dict(ledger.cash),
                settled_positions=dict(ledger.settled),
                breaks=breaks,
                register=register,
                checks=checks,
            )
        )
        previous_day, previous_nav, previous_nps, previous_rates = day, class_total, nps_today, rates

    result.events = pd.DataFrame(ledger.events)
    return result
