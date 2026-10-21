"""Reading a fund's input files, and downloading ECB reference rates.

A fund lives in one folder:

    fund.json                  fund setup: share classes, fees, holidays, tolerances
    opening.json               positions, cash, accruals and share classes at the start
    securities.csv             isin, name, currency
    prices.csv                 date, isin, price               (local currency)
    fx.csv                     date, currency, rate            (units per one unit of base currency)
    trades.csv                 trade_id, trade_date, settle_date, isin, side, quantity, price, commission, broker
    dividends.csv              isin, ex_date, pay_date, amount_per_share, withholding_rate
    deals.csv                  deal_id, deal_date, share_class, type, amount, units, investor
    custodian_positions.csv    date, isin, quantity            (settled positions)
    custodian_cash.csv         date, currency, balance
    broker_confirms.csv        confirm_id, received, status, client_ref, trade_date, settle_date,
                               isin, side, quantity, price, net_amount, currency, broker
"""

from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
from dataclasses import dataclass

import pandas as pd

from .models import ClassState, Expense, FundConfig, ShareClass, Tolerances
from .money import round_money

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"
    "?startPeriod={start}&endPeriod={end}&format=csvdata"
)
USER_AGENT = "fund-nav-engine/0.1"

# ---------------------------------------------------------------------------
# Fund setup
# ---------------------------------------------------------------------------


def _date(text) -> dt.date:
    return dt.date.fromisoformat(str(text)[:10])


def load_config(path: pathlib.Path | str) -> FundConfig:
    raw = json.loads(pathlib.Path(path).read_text())
    classes = tuple(
        ShareClass(
            code=c["code"],
            currency=c["currency"],
            management_fee=float(c["management_fee"]),
            performance_fee=float(c["performance_fee"]) if c.get("performance_fee") is not None else None,
        )
        for c in raw["share_classes"]
    )
    expenses = tuple(
        Expense(name=e["name"], annual_rate=e.get("annual_rate"), annual_amount=e.get("annual_amount"))
        for e in raw.get("expenses", [])
    )
    for e in expenses:
        if (e.annual_rate is None) == (e.annual_amount is None):
            raise ValueError(f"expense {e.name!r} needs exactly one of annual_rate and annual_amount")
    return FundConfig(
        name=raw["name"],
        base_currency=raw["base_currency"],
        share_classes=classes,
        expenses=expenses,
        holidays=tuple(_date(d) for d in raw.get("holidays", [])),
        tolerances=Tolerances(**raw.get("tolerances", {})),
        nav_decimals=int(raw.get("nav_decimals", 4)),
        unit_decimals=int(raw.get("unit_decimals", 3)),
        capital_settlement_days=int(raw.get("capital_settlement_days", 3)),
    )


@dataclass(frozen=True)
class Opening:
    date: dt.date
    positions: dict[str, float]
    cash: dict[str, float]
    expenses_accrued: dict[str, float]
    management_fees_accrued: dict[str, float]
    share_classes: dict[str, ClassState]


def load_opening(path: pathlib.Path | str) -> Opening:
    raw = json.loads(pathlib.Path(path).read_text())
    classes = {
        code: ClassState(
            code=code,
            units=float(c["units"]),
            nav=float(c["nav"]),
            high_water_mark=c.get("high_water_mark"),
            performance_fee_accrued=float(c.get("performance_fee_accrued", 0.0)),
        )
        for code, c in raw["share_classes"].items()
    }
    return Opening(
        date=_date(raw["date"]),
        positions={k: float(v) for k, v in raw["positions"].items()},
        cash={k: float(v) for k, v in raw["cash"].items()},
        expenses_accrued={k: float(v) for k, v in raw.get("expenses_accrued", {}).items()},
        management_fees_accrued={k: float(v) for k, v in raw.get("management_fees_accrued", {}).items()},
        share_classes=classes,
    )


# ---------------------------------------------------------------------------
# Daily files
# ---------------------------------------------------------------------------


def _read(folder: pathlib.Path, name: str, dates: tuple[str, ...] = ()) -> pd.DataFrame:
    path = folder / name
    if not path.exists():
        raise FileNotFoundError(f"missing input file: {path}")
    frame = pd.read_csv(path, dtype={"isin": str, "client_ref": str, "trade_id": str, "deal_id": str})
    for column in dates:
        frame[column] = pd.to_datetime(frame[column]).dt.date
    return frame


@dataclass
class FundData:
    config: FundConfig
    opening: Opening
    securities: pd.DataFrame  # indexed by isin
    prices: pd.DataFrame
    fx: pd.DataFrame
    trades: pd.DataFrame
    dividends: pd.DataFrame
    deals: pd.DataFrame
    custodian_positions: pd.DataFrame
    custodian_cash: pd.DataFrame
    confirms: pd.DataFrame

    def __post_init__(self) -> None:
        self._prices = {d: dict(zip(g["isin"], g["price"])) for d, g in self.prices.groupby("date")}
        self._fx = {d: dict(zip(g["currency"], g["rate"])) for d, g in self.fx.groupby("date")}
        self._cust_pos = {d: dict(zip(g["isin"], g["quantity"])) for d, g in self.custodian_positions.groupby("date")}
        self._cust_cash = {d: dict(zip(g["currency"], g["balance"])) for d, g in self.custodian_cash.groupby("date")}

    def prices_on(self, day: dt.date) -> dict[str, float]:
        return dict(self._prices.get(day, {}))

    def fx_on(self, day: dt.date) -> dict[str, float]:
        return dict(self._fx.get(day, {}))

    def custodian_positions_on(self, day: dt.date) -> dict[str, float] | None:
        return dict(self._cust_pos[day]) if day in self._cust_pos else None

    def custodian_cash_on(self, day: dt.date) -> dict[str, float] | None:
        return dict(self._cust_cash[day]) if day in self._cust_cash else None

    def live_confirms(self, day: dt.date) -> pd.DataFrame:
        """Each confirmation as it stood at the end of `day`: the latest version
        received by then, with canceled confirmations left out."""
        received = self.confirms[self.confirms["received"] <= day]
        if received.empty:
            return received.copy()
        latest = received.sort_values(["confirm_id", "received"]).groupby("confirm_id").tail(1)
        return latest[latest["status"].str.upper() != "CANCEL"].reset_index(drop=True)

    def booked_trades(self, day: dt.date) -> pd.DataFrame:
        """Trades with a trade date up to `day`, with net amount and currency added."""
        return self.trades[self.trades["trade_date"] <= day].reset_index(drop=True)


def _add_net_amounts(trades: pd.DataFrame, securities: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades["currency"] = trades["isin"].map(securities["currency"])
    consideration = [round_money(q * p) for q, p in zip(trades["quantity"], trades["price"])]
    sign = trades["side"].str.upper().map({"BUY": 1.0, "SELL": -1.0})
    trades["net_amount"] = [round_money(c + s * fee) for c, s, fee in zip(consideration, sign, trades["commission"])]
    return trades


def load_fund(folder: pathlib.Path | str = SAMPLE_DIR) -> FundData:
    folder = pathlib.Path(folder)
    config = load_config(folder / "fund.json")
    securities = _read(folder, "securities.csv").set_index("isin")
    trades = _read(folder, "trades.csv", ("trade_date", "settle_date"))
    return FundData(
        config=config,
        opening=load_opening(folder / "opening.json"),
        securities=securities,
        prices=_read(folder, "prices.csv", ("date",)),
        fx=_read(folder, "fx.csv", ("date",)),
        trades=_add_net_amounts(trades, securities),
        dividends=_read(folder, "dividends.csv", ("ex_date", "pay_date")),
        deals=_read(folder, "deals.csv", ("deal_date",)),
        custodian_positions=_read(folder, "custodian_positions.csv", ("date",)),
        custodian_cash=_read(folder, "custodian_cash.csv", ("date",)),
        confirms=_read(folder, "broker_confirms.csv", ("received", "trade_date", "settle_date")),
    )


# ---------------------------------------------------------------------------
# ECB reference rates
# ---------------------------------------------------------------------------


def ecb_url(currencies: list[str], start: dt.date, end: dt.date) -> str:
    return ECB_URL.format(currencies="+".join(c.upper() for c in currencies), start=start, end=end)


def parse_ecb_csv(text: str) -> pd.DataFrame:
    """The ECB Data Portal's CSV output as date, currency, rate.

    Rates are units of each currency per one euro, the same convention as fx.csv.
    """
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [c.strip().upper() for c in frame.columns]
    missing = {"CURRENCY", "TIME_PERIOD", "OBS_VALUE"} - set(frame.columns)
    if missing:
        raise ValueError(f"not an ECB rates file, missing {sorted(missing)}")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(frame["TIME_PERIOD"]).dt.date,
            "currency": frame["CURRENCY"].astype(str).str.upper(),
            "rate": pd.to_numeric(frame["OBS_VALUE"], errors="coerce"),
        }
    )
    return out.dropna().sort_values(["date", "currency"]).reset_index(drop=True)


def download_fx(currencies: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
    import requests

    response = requests.get(ecb_url(currencies, start, end), headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return parse_ecb_csv(response.text)
