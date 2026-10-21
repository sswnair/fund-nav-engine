"""The fund's books: positions, cash, amounts due in and out, and accrued fees.

Trades are booked on trade date. Cash and settled positions move on the
contractual settlement date, so a trade that fails at the custodian shows up
as a reconciliation break rather than as a change in the books.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .data import FundData
from .money import round_money

ZERO = 1e-9


@dataclass
class Item:
    """An amount due to or from the fund."""

    kind: str  # sale, purchase, income, subscription, redemption
    currency: str
    amount: float  # positive
    due: dt.date
    isin: str | None = None
    quantity: float = 0.0


@dataclass
class Ledger:
    base: str
    traded: dict[str, float]  # positions on trade date
    settled: dict[str, float]  # positions on settlement date
    cash: dict[str, float]  # settled cash
    receivables: dict[str, Item] = field(default_factory=dict)
    payables: dict[str, Item] = field(default_factory=dict)
    expenses_accrued: dict[str, float] = field(default_factory=dict)  # base currency
    management_fees_accrued: dict[str, float] = field(default_factory=dict)  # base currency, by class
    performance_fees_accrued: dict[str, float] = field(default_factory=dict)  # base currency, by class
    performance_fees_payable: dict[str, float] = field(default_factory=dict)  # base currency, by class
    events: list[dict] = field(default_factory=list)

    @classmethod
    def open(cls, data: FundData) -> "Ledger":
        o = data.opening
        return cls(
            base=data.config.base_currency,
            traded=dict(o.positions),
            settled=dict(o.positions),
            cash=dict(o.cash),
            expenses_accrued={e.name: o.expenses_accrued.get(e.name, 0.0) for e in data.config.expenses},
            management_fees_accrued={c.code: o.management_fees_accrued.get(c.code, 0.0) for c in data.config.share_classes},
            performance_fees_accrued={code: s.performance_fee_accrued for code, s in o.share_classes.items()},
            performance_fees_payable={c.code: 0.0 for c in data.config.share_classes},
        )

    # ------------------------------------------------------------------
    # Daily events
    # ------------------------------------------------------------------

    def _log(self, day, kind, reference, currency, amount, detail="") -> None:
        self.events.append(
            {"date": day, "event": kind, "reference": reference, "currency": currency, "amount": round_money(amount), "detail": detail}
        )

    @staticmethod
    def _add(book: dict[str, float], key: str, amount: float) -> None:
        book[key] = book.get(key, 0.0) + amount
        if abs(book[key]) < ZERO:
            del book[key]

    def apply_day(self, day: dt.date, data: FundData, first_of_month: bool) -> None:
        """Book everything that happens on a valuation day, before valuation."""
        currency_of = data.securities["currency"]

        # Dividends going ex today: entitlement is the position before today's trades.
        for d in data.dividends[data.dividends["ex_date"] == day].itertuples():
            held = self.traded.get(d.isin, 0.0)
            if held <= ZERO:
                continue
            ccy = currency_of[d.isin]
            net = round_money(held * d.amount_per_share * (1 - d.withholding_rate))
            self.receivables[f"DIV|{d.isin}|{d.ex_date}"] = Item("income", ccy, net, d.pay_date, d.isin, held)
            self._log(day, "dividend accrued", d.isin, ccy, net, f"{held:,.0f} shares, {d.withholding_rate:.0%} withholding")

        # Trades on trade date.
        for t in data.trades[data.trades["trade_date"] == day].itertuples():
            sign = 1.0 if t.side.upper() == "BUY" else -1.0
            self._add(self.traded, t.isin, sign * t.quantity)
            item = Item("purchase" if sign > 0 else "sale", t.currency, t.net_amount, t.settle_date, t.isin, t.quantity)
            (self.payables if sign > 0 else self.receivables)[t.trade_id] = item
            self._log(day, "trade", t.trade_id, t.currency, t.net_amount, f"{t.side.lower()} {t.quantity:,.0f} {t.isin}")

        # Settlements, income and capital due today.
        for key, item in list(self.receivables.items()):
            if item.due != day:
                continue
            if item.kind == "sale":
                self._add(self.settled, item.isin, -item.quantity)
            self._add(self.cash, item.currency, item.amount)
            del self.receivables[key]
            self._log(day, f"{item.kind} settled", key, item.currency, item.amount)
        for key, item in list(self.payables.items()):
            if item.due != day:
                continue
            if item.kind == "purchase":
                self._add(self.settled, item.isin, item.quantity)
            self._add(self.cash, item.currency, -item.amount)
            del self.payables[key]
            self._log(day, f"{item.kind} settled", key, item.currency, -item.amount)

        # Fees accrued last month are paid on the first valuation day of the next.
        if first_of_month:
            total = 0.0
            for book in (self.expenses_accrued, self.management_fees_accrued, self.performance_fees_payable):
                for name, amount in book.items():
                    if amount:
                        self._log(day, "fee paid", name, self.base, -amount)
                        total += amount
                        book[name] = 0.0
            if total:
                self._add(self.cash, self.base, -round_money(total))

    # ------------------------------------------------------------------
    # Postings from the NAV calculation
    # ------------------------------------------------------------------

    def post_expense(self, name: str, amount: float) -> None:
        self.expenses_accrued[name] = round_money(self.expenses_accrued.get(name, 0.0) + amount)

    def post_management_fee(self, code: str, amount: float) -> None:
        self.management_fees_accrued[code] = round_money(self.management_fees_accrued.get(code, 0.0) + amount)

    def set_performance_fee(self, code: str, accrued: float) -> None:
        self.performance_fees_accrued[code] = round_money(accrued)

    def crystallize(self, code: str, amount: float) -> None:
        """Move part or all of a class's accrued performance fee to payable."""
        self.performance_fees_payable[code] = round_money(self.performance_fees_payable.get(code, 0.0) + amount)
        self.performance_fees_accrued[code] = round_money(self.performance_fees_accrued.get(code, 0.0) - amount)

    def book_subscription(self, deal_id: str, currency: str, amount: float, due: dt.date) -> None:
        self.receivables[deal_id] = Item("subscription", currency, amount, due)

    def book_redemption(self, deal_id: str, currency: str, amount: float, due: dt.date) -> None:
        self.payables[deal_id] = Item("redemption", currency, amount, due)

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def items(self, side: str, kind: str) -> list[tuple[str, Item]]:
        book = self.receivables if side == "receivable" else self.payables
        return [(key, item) for key, item in book.items() if item.kind == kind]
