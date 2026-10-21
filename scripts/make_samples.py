"""Write the synthetic sample fund in data/sample.

Every company, price, trade and investor in the sample is made up. The run
covers the fourth quarter of 2025 so the year-end performance fee falls
inside it.

The custodian statements and broker confirmations start as a copy of the
fund's own books, which is why this script runs the engine, and then get a
known set of differences added. Those differences are listed in
expected_breaks.csv, which the tests compare with what the reconciliation
finds. Run from the project root after `pip install -e .`:

    python scripts/make_samples.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import numpy as np
import pandas as pd

from fundnav.data import load_fund
from fundnav.dates import add_valuation_days, valuation_days
from fundnav.engine import run
from fundnav.money import round_half_up, round_money

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sample"
SEED = 20251231

OPENING = dt.date(2025, 9, 30)
END = dt.date(2025, 12, 31)
HOLIDAYS = [dt.date(2025, 10, 27), dt.date(2025, 12, 25), dt.date(2025, 12, 26), dt.date(2026, 1, 1)]

FUND = {
    "name": "Sample Global Equity Fund",
    "base_currency": "EUR",
    "nav_decimals": 4,
    "unit_decimals": 3,
    "capital_settlement_days": 3,
    "share_classes": [
        {"code": "A-EUR", "currency": "EUR", "management_fee": 0.015},
        {"code": "I-EUR", "currency": "EUR", "management_fee": 0.0075, "performance_fee": 0.10},
        {"code": "I-USD", "currency": "USD", "management_fee": 0.0075, "performance_fee": 0.10},
    ],
    "expenses": [
        {"name": "Administration", "annual_rate": 0.0005},
        {"name": "Depositary", "annual_rate": 0.0002},
        {"name": "Audit", "annual_amount": 24000.0},
    ],
    "holidays": [d.isoformat() for d in HOLIDAYS],
    "tolerances": {"cash": 5.0, "price": 0.0001, "amount": 1.0},
}

# name, currency, opening price, annual drift, annual volatility
SECURITIES = [
    ("Alder Industrials SA", "EUR", 84.20, 0.06, 0.22),
    ("Beech Energy SE", "EUR", 31.55, 0.02, 0.26),
    ("Cedar Logistics NV", "EUR", 57.80, 0.04, 0.24),
    ("Elm Semiconductors NV", "EUR", 142.60, 0.12, 0.34),
    ("Holly Insurance AG", "EUR", 212.40, 0.05, 0.18),
    ("Fir Software Inc", "USD", 318.75, 0.14, 0.30),
    ("Hazel Health Corp", "USD", 96.40, 0.05, 0.24),
    ("Juniper Payments Inc", "USD", 61.15, 0.08, 0.28),
    ("Larch Cloud Inc", "USD", 188.30, 0.16, 0.38),
    ("Maple Retail Corp", "USD", 74.90, 0.04, 0.20),
    ("Oak Telecom plc", "GBP", 4.62, 0.01, 0.18),
    ("Pine Brewing plc", "GBP", 18.35, 0.03, 0.20),
    ("Rowan Pharma AG", "CHF", 246.80, 0.06, 0.20),
    ("Spruce Watches SA", "CHF", 132.10, 0.05, 0.22),
    ("Willow Robotics Inc", "USD", 42.70, 0.18, 0.40),  # bought during the quarter
]
OPENING_FX = {"USD": 1.1740, "GBP": 0.8730, "CHF": 0.9360}
FX_VOL = {"USD": 0.060, "GBP": 0.045, "CHF": 0.040}


def isin(number: int) -> str:
    """A well-formed ISIN with the unassigned country prefix XX, so it can never clash with a real one."""
    body = f"XX{number:09d}"
    digits = "".join(str(int(ch, 36)) for ch in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return body + str((10 - total % 10) % 10)


def simulate_markets(rng: np.random.Generator):
    days = pd.bdate_range(OPENING, END).date
    n = len(days)
    market = rng.normal(0.0003, 0.008, n)
    prices = {}
    for i, (name, ccy, p0, drift, vol) in enumerate(SECURITIES):
        beta = 0.8 + 0.4 * rng.random()
        idio = rng.standard_t(5, n) / np.sqrt(5 / 3) * vol / np.sqrt(252) * 0.8
        r = drift / 252 + beta * market + idio
        r[0] = 0.0
        prices[isin(1001 + i)] = p0 * np.cumprod(1 + r)
    fx = {}
    for ccy, f0 in OPENING_FX.items():
        r = rng.normal(0, FX_VOL[ccy] / np.sqrt(252), n)
        r[0] = 0.0
        fx[ccy] = f0 * np.cumprod(1 + r)
    return days, prices, fx


def price_decimals(ccy: str) -> int:
    return 4 if ccy == "GBP" else 2


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    vdays = valuation_days(OPENING, END, HOLIDAYS)
    calendar_days, raw_prices, raw_fx = simulate_markets(rng)
    index_of = {d: i for i, d in enumerate(calendar_days)}

    securities = pd.DataFrame(
        {"isin": [isin(1001 + i) for i in range(len(SECURITIES))], "name": [s[0] for s in SECURITIES], "currency": [s[1] for s in SECURITIES]}
    )
    ccy_of = dict(zip(securities["isin"], securities["currency"]))
    names = dict(zip(securities["name"], securities["isin"]))

    # Two things for the day-end checks to catch: a price that stops updating
    # for four days, and a genuine one-day fall of 14%.
    stale_isin = names["Pine Brewing plc"]
    stale_days = [d for d in vdays if dt.date(2025, 11, 17) <= d <= dt.date(2025, 11, 20)]
    drop_isin, drop_day = names["Hazel Health Corp"], dt.date(2025, 11, 6)
    k = index_of[drop_day]
    raw_prices[drop_isin][k:] *= 0.86 / (raw_prices[drop_isin][k] / raw_prices[drop_isin][k - 1])

    price_rows = []
    for d in vdays:
        i = index_of[d]
        for code, path in raw_prices.items():
            ccy = ccy_of[code]
            price = path[i]
            if code == stale_isin and d in stale_days:
                price = raw_prices[code][index_of[stale_days[0]] - 1]
            price_rows.append((d, code, round_half_up(float(price), price_decimals(ccy))))
    prices = pd.DataFrame(price_rows, columns=["date", "isin", "price"])
    fx = pd.DataFrame(
        [(d, ccy, round_half_up(float(raw_fx[ccy][index_of[d]]), 4)) for d in vdays for ccy in OPENING_FX],
        columns=["date", "currency", "rate"],
    )
    price_on = {(d, c): p for d, c, p in prices.itertuples(index=False)}
    fx_on = {(d, c): r for d, c, r in fx.itertuples(index=False)}

    # ------------------------------------------------------------------
    # Opening state: September 30, 2025
    # ------------------------------------------------------------------
    target = {"A-EUR": 81_000_000.00, "I-EUR": 63_000_000.00, "I-USD": 36_000_000.00}
    total = sum(target.values())
    held_at_open = [code for code in securities["isin"] if code != names["Willow Robotics Inc"]]
    weight = 0.94 / len(held_at_open)
    positions = {}
    for code in held_at_open:
        ccy = ccy_of[code]
        rate = 1.0 if ccy == "EUR" else fx_on[(OPENING, ccy)]
        qty = weight * total * rate / price_on[(OPENING, code)]
        positions[code] = float(round(qty, -1))

    eurusd = fx_on[(OPENING, "USD")]
    classes = {
        "A-EUR": {"units": round(target["A-EUR"] / 112.4530, 3), "nav": target["A-EUR"], "high_water_mark": None, "performance_fee_accrued": 0.0},
        "I-EUR": {"units": round(target["I-EUR"] / 128.0400, 3), "nav": target["I-EUR"], "high_water_mark": 121.50},
        "I-USD": {"units": round(target["I-USD"] * eurusd / 141.3700, 3), "nav": target["I-USD"], "high_water_mark": 133.80},
    }
    for code in ("I-EUR", "I-USD"):
        c = classes[code]
        rate = eurusd if code == "I-USD" else 1.0
        # Accrued fee consistent with the class's net NAV: solve nav = gross - 10% x (gross - HWM x units / rate).
        gross = (c["nav"] - 0.10 * c["high_water_mark"] * c["units"] / rate) / 0.90
        c["performance_fee_accrued"] = round_money(gross - c["nav"])

    september = 30
    management = {code: round_money(target[code] * fee * september / 365) for code, fee in (("A-EUR", 0.015), ("I-EUR", 0.0075), ("I-USD", 0.0075))}
    expenses = {
        "Administration": round_money(total * 0.0005 * september / 365),
        "Depositary": round_money(total * 0.0002 * september / 365),
        "Audit": round_money(24000 * september / 365),
    }
    liabilities = sum(management.values()) + sum(expenses.values()) + sum(c["performance_fee_accrued"] for c in classes.values())
    cash = {"USD": 1_250_000.00, "GBP": 240_000.00, "CHF": 1_750_000.00}
    invested = sum(round_money(round_money(q * price_on[(OPENING, code)]) / (1.0 if ccy_of[code] == "EUR" else fx_on[(OPENING, ccy_of[code])])) for code, q in positions.items())
    other_cash = sum(round_money(v / fx_on[(OPENING, c)]) for c, v in cash.items())
    cash = {"EUR": round_money(total + liabilities - invested - other_cash), **cash}

    opening = {
        "date": OPENING.isoformat(),
        "positions": positions,
        "cash": cash,
        "expenses_accrued": expenses,
        "management_fees_accrued": management,
        "share_classes": classes,
    }

    # ------------------------------------------------------------------
    # Trades, dividends and investor dealing
    # ------------------------------------------------------------------
    trade_plan = [
        # (trade date, security, side, quantity)
        ("2025-10-02", "Elm Semiconductors NV", "BUY", 6000),
        ("2025-10-07", "Beech Energy SE", "SELL", 40000),
        ("2025-10-09", "Fir Software Inc", "BUY", 2500),
        ("2025-10-10", "Willow Robotics Inc", "BUY", 60000),
        ("2025-10-15", "Holly Insurance AG", "SELL", 3000),
        ("2025-10-21", "Rowan Pharma AG", "BUY", 4000),
        ("2025-10-23", "Juniper Payments Inc", "BUY", 15000),
        ("2025-10-29", "Oak Telecom plc", "SELL", 250000),
        ("2025-11-04", "Larch Cloud Inc", "SELL", 5700),
        ("2025-11-07", "Hazel Health Corp", "BUY", 12000),
        ("2025-11-11", "Alder Industrials SA", "BUY", 9000),
        ("2025-11-14", "Maple Retail Corp", "SELL", 20000),
        ("2025-11-18", "Spruce Watches SA", "BUY", 5000),
        ("2025-11-21", "Pine Brewing plc", "SELL", 60000),
        ("2025-11-25", "Cedar Logistics NV", "SELL", 90000),
        ("2025-11-28", "Willow Robotics Inc", "BUY", 30000),
        ("2025-12-02", "Elm Semiconductors NV", "SELL", 4000),
        ("2025-12-04", "Fir Software Inc", "SELL", 1500),
        ("2025-12-08", "Holly Insurance AG", "BUY", 2500),
        ("2025-12-10", "Juniper Payments Inc", "SELL", 10000),
        ("2025-12-12", "Rowan Pharma AG", "SELL", 3000),
        ("2025-12-16", "Beech Energy SE", "BUY", 30000),
        ("2025-12-18", "Cedar Logistics NV", "SELL", None),  # sells what is left
        ("2025-12-22", "Larch Cloud Inc", "BUY", 3000),
        ("2025-12-29", "Maple Retail Corp", "BUY", 8000),
        ("2025-12-30", "Alder Industrials SA", "BUY", 5000),  # settles in January
    ]
    brokers = ["Heron Markets", "Kestrel Securities"]
    held = dict(positions)
    trades = []
    for n, (day, name, side, qty) in enumerate(trade_plan, start=1):
        d = dt.date.fromisoformat(day)
        code = names[name]
        if qty is None:
            qty = held[code]
        held[code] = held.get(code, 0.0) + (qty if side == "BUY" else -qty)
        ccy = ccy_of[code]
        slip = 1 + rng.normal(0, 0.002)
        price = round_half_up(price_on[(d, code)] * slip, price_decimals(ccy))
        commission = round_money(max(10.0, qty * price * 0.0005))
        trades.append(
            {
                "trade_id": f"T{n:04d}",
                "trade_date": d,
                "settle_date": add_valuation_days(d, 2, HOLIDAYS),
                "isin": code,
                "side": side,
                "quantity": float(qty),
                "price": price,
                "commission": commission,
                "broker": brokers[n % 2],
            }
        )
    trades = pd.DataFrame(trades)

    dividends = pd.DataFrame(
        [
            (names["Fir Software Inc"], "2025-10-15", "2025-10-30", 0.42, 0.15),
            (names["Alder Industrials SA"], "2025-10-23", "2025-10-28", 1.10, 0.0),
            (names["Oak Telecom plc"], "2025-11-06", "2025-12-04", 0.0615, 0.0),
            (names["Juniper Payments Inc"], "2025-11-13", "2025-11-20", 0.30, 0.15),
            (names["Rowan Pharma AG"], "2025-12-03", "2025-12-09", 2.80, 0.35),
            (names["Maple Retail Corp"], "2025-12-10", "2025-12-22", 0.55, 0.15),
        ],
        columns=["isin", "ex_date", "pay_date", "amount_per_share", "withholding_rate"],
    )

    deals = pd.DataFrame(
        [
            ("D0001", "2025-10-02", "A-EUR", "subscription", 250000.00, None, "INV-1021"),
            ("D0002", "2025-10-09", "I-USD", "subscription", 3000000.00, None, "INV-2004"),
            ("D0003", "2025-10-16", "A-EUR", "redemption", None, 1250.000, "INV-1007"),
            ("D0004", "2025-10-23", "I-EUR", "subscription", 5000000.00, None, "INV-3011"),
            ("D0005", "2025-11-04", "A-EUR", "subscription", 120000.00, None, "INV-1033"),
            ("D0006", "2025-11-12", "I-USD", "redemption", None, 4000.000, "INV-2001"),
            ("D0007", "2025-11-19", "A-EUR", "redemption", None, 2000.000, "INV-1012"),
            ("D0008", "2025-11-27", "I-EUR", "subscription", 2500000.00, None, "INV-3004"),
            ("D0009", "2025-12-03", "A-EUR", "subscription", 75000.00, None, "INV-1040"),
            ("D0010", "2025-12-11", "I-EUR", "redemption", None, 25000.000, "INV-3002"),
            ("D0011", "2025-12-17", "I-USD", "subscription", 1500000.00, None, "INV-2009"),
            ("D0012", "2025-12-22", "A-EUR", "redemption", None, 800.000, "INV-1018"),
            ("D0013", "2025-12-30", "A-EUR", "subscription", 180000.00, None, "INV-1046"),
        ],
        columns=["deal_id", "deal_date", "share_class", "type", "amount", "units", "investor"],
    )

    # ------------------------------------------------------------------
    # Write everything except the custodian and broker files, then run the
    # books once to see what those files should say if nothing went wrong.
    # ------------------------------------------------------------------
    (OUT / "fund.json").write_text(json.dumps(FUND, indent=2) + "\n")
    (OUT / "opening.json").write_text(json.dumps(opening, indent=2) + "\n")
    securities.to_csv(OUT / "securities.csv", index=False)
    pd.concat([prices.assign(date=prices["date"].astype(str))], ignore_index=True).to_csv(OUT / "prices.csv", index=False)
    fx.to_csv(OUT / "fx.csv", index=False)
    trades.to_csv(OUT / "trades.csv", index=False)
    dividends.to_csv(OUT / "dividends.csv", index=False)
    deals.to_csv(OUT / "deals.csv", index=False)
    for name, columns in (
        ("custodian_positions.csv", ["date", "isin", "quantity"]),
        ("custodian_cash.csv", ["date", "currency", "balance"]),
        (
            "broker_confirms.csv",
            ["confirm_id", "received", "status", "client_ref", "trade_date", "settle_date", "isin", "side",
             "quantity", "price", "net_amount", "currency", "broker"],
        ),
    ):
        pd.DataFrame(columns=columns).to_csv(OUT / name, index=False)

    books = run(load_fund(OUT))
    trades_full = load_fund(OUT).trades.set_index("trade_id")

    # ------------------------------------------------------------------
    # Custodian statements: the books, plus what went wrong at the custodian
    # ------------------------------------------------------------------
    expected = []
    failed = trades_full.loc["T0004"]  # first purchase of Willow Robotics
    failed_until = add_valuation_days(failed.settle_date, 3, HOLIDAYS)
    expected += [
        (f"POSITION|{failed['isin']}", "missing at custodian", failed.settle_date, failed_until),
        ("CASH|USD", "balance", failed.settle_date, failed_until),
    ]
    fee_day = dt.date(2025, 11, 5)
    expected.append(("CASH|EUR", "balance", fee_day, None))
    juniper = dividends.iloc[3]
    wht_day = dt.date.fromisoformat(juniper.pay_date)
    ex_day = dt.date.fromisoformat(juniper.ex_date)
    held_ex = positions.get(juniper["isin"], 0.0) + sum(
        (t.quantity if t.side == "BUY" else -t.quantity)
        for t in trades.itertuples()
        if t.isin == juniper["isin"] and t.trade_date < ex_day
    )
    withheld_extra = round_money(held_ex * juniper.amount_per_share * 0.15)
    expected.append(("CASH|USD", "balance", wht_day, None))
    scrip_isin, scrip_day = names["Spruce Watches SA"], dt.date(2025, 12, 15)
    expected.append((f"POSITION|{scrip_isin}", "quantity", scrip_day, None))
    gbp_day = dt.date(2025, 12, 4)

    pos_rows, cash_rows = [], []
    for d in books.days:
        settled = dict(d.settled_positions)
        cash = dict(d.cash)
        if failed.settle_date <= d.date < failed_until:
            settled[failed["isin"]] = settled.get(failed["isin"], 0.0) - failed.quantity
            cash["USD"] = cash.get("USD", 0.0) + failed.net_amount
        if d.date >= fee_day:
            cash["EUR"] -= 37.50  # custody charge the books have not picked up
        if d.date >= wht_day:
            cash["USD"] -= withheld_extra  # withheld at 30%, not 15%
        if d.date >= scrip_day:
            settled[scrip_isin] = settled[scrip_isin] + 100  # scrip dividend booked at the custodian only
        if d.date >= gbp_day:
            cash["GBP"] += 0.40  # rounding on the dividend, inside tolerance
        for code, qty in sorted(settled.items()):
            if abs(qty) > 1e-9:
                pos_rows.append((d.date, code, qty))
        for ccy, bal in sorted(cash.items()):
            cash_rows.append((d.date, ccy, round_money(bal)))
    pd.DataFrame(pos_rows, columns=["date", "isin", "quantity"]).to_csv(OUT / "custodian_positions.csv", index=False)
    pd.DataFrame(cash_rows, columns=["date", "currency", "balance"]).to_csv(OUT / "custodian_cash.csv", index=False)

    # ------------------------------------------------------------------
    # Broker confirmations: one per trade, received on trade date, with a
    # handful of problems and the corrections that clear them.
    # ------------------------------------------------------------------
    confirms = []

    def confirm(t, n, received, status="NEW", **changes):
        row = {
            "confirm_id": f"C{70000 + n}",
            "received": received,
            "status": status,
            "client_ref": t.name,
            "trade_date": t.trade_date,
            "settle_date": t.settle_date,
            "isin": t["isin"],
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "net_amount": t.net_amount,
            "currency": t.currency,
            "broker": t.broker,
        }
        row.update(changes)
        confirms.append(row)

    late = {"T0014": 6}
    for n, (trade_id, t) in enumerate(trades_full.iterrows(), start=1):
        sign = 1 if t.side == "BUY" else -1
        if trade_id == "T0003":  # price wrong on the confirm, amended two days later
            bad = round_half_up(t.price * 1.0006, 2)
            confirm(t, n, t.trade_date, price=bad, net_amount=round_money(round_money(t.quantity * bad) + sign * t.commission))
            confirm(t, n, add_valuation_days(t.trade_date, 2, HOLIDAYS), "AMEND")
            expected.append((f"TRADE|{trade_id}", "price, net amount", t.trade_date, add_valuation_days(t.trade_date, 2, HOLIDAYS)))
        elif trade_id == "T0009":  # quantity keyed wrong by the broker, amended next day
            confirm(t, n, t.trade_date, quantity=t.quantity + 1800,
                    net_amount=round_money(round_money((t.quantity + 1800) * t.price) + sign * t.commission))
            confirm(t, n, add_valuation_days(t.trade_date, 1, HOLIDAYS), "AMEND")
            expected.append((f"TRADE|{trade_id}", "quantity, net amount", t.trade_date, add_valuation_days(t.trade_date, 1, HOLIDAYS)))
        elif trade_id in late:  # confirmation arrives six business days late
            arrives = add_valuation_days(t.trade_date, late[trade_id], HOLIDAYS)
            confirm(t, n, arrives)
            expected.append((f"TRADE|{trade_id}", "no confirm", t.trade_date, arrives))
        elif trade_id == "T0018":  # broker has T+3, the fund T+2
            confirm(t, n, t.trade_date, settle_date=add_valuation_days(t.trade_date, 3, HOLIDAYS))
            confirm(t, n, add_valuation_days(t.trade_date, 1, HOLIDAYS), "AMEND")
            expected.append((f"TRADE|{trade_id}", "settlement date", t.trade_date, add_valuation_days(t.trade_date, 1, HOLIDAYS)))
        elif trade_id == "T0022":  # broker charged 45.00 more commission; still in dispute at year end
            confirm(t, n, t.trade_date, net_amount=round_money(t.net_amount + sign * 45.00))
            expected.append((f"TRADE|{trade_id}", "net amount", t.trade_date, None))
        else:
            confirm(t, n, t.trade_date)

    stray = dt.date(2025, 11, 26)
    stray_cancel = dt.date(2025, 12, 2)
    other = {
        "confirm_id": "C79001", "received": stray, "status": "NEW", "client_ref": "T9112",
        "trade_date": stray, "settle_date": add_valuation_days(stray, 2, HOLIDAYS),
        "isin": names["Maple Retail Corp"], "side": "BUY", "quantity": 4000.0, "price": 77.15,
        "net_amount": 308754.30, "currency": "USD", "broker": "Kestrel Securities",
    }
    confirms.append(other)
    confirms.append({**other, "received": stray_cancel, "status": "CANCEL"})
    expected.append(("CONFIRM|C79001", "no trade", stray, stray_cancel))

    pd.DataFrame(confirms).sort_values(["received", "confirm_id"]).to_csv(OUT / "broker_confirms.csv", index=False)
    pd.DataFrame(expected, columns=["key", "detail", "first_seen", "resolved_on"]).sort_values(["first_seen", "key"]).to_csv(
        OUT / "expected_breaks.csv", index=False
    )
    print(f"Wrote the sample fund to {OUT}")


if __name__ == "__main__":
    main()
