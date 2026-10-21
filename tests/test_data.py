"""Reading the fund's files and the ECB rates format."""

import datetime as dt

import pytest

from fundnav.data import ecb_url, load_config, parse_ecb_csv
from fundnav.data import SAMPLE_DIR

ECB_SAMPLE = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2025-10-01,1.1734,A\n"
    "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2025-10-01,0.87245,A\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2025-10-02,1.1691,A\n"
)


def test_config(sample):
    config = sample.config
    assert config.base_currency == "EUR"
    assert [c.code for c in config.share_classes] == ["A-EUR", "I-EUR", "I-USD"]
    assert config.share_class("I-USD").currency == "USD"
    assert config.share_class("A-EUR").performance_fee is None
    assert dt.date(2025, 10, 27) in config.holidays
    assert config.tolerances.cash == 5.0


def test_expense_needs_a_rate_or_an_amount(tmp_path):
    text = (SAMPLE_DIR / "fund.json").read_text().replace('"annual_amount": 24000.0', '"annual_amount": null')
    path = tmp_path / "fund.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_config(path)


def test_opening_balances(sample):
    opening = sample.opening
    assert opening.date == dt.date(2025, 9, 30)
    assert sum(s.nav for s in opening.share_classes.values()) == pytest.approx(180_000_000.00)
    assert opening.share_classes["I-EUR"].high_water_mark == 121.50


def test_trades_get_net_amounts(sample):
    t = sample.trades.set_index("trade_id").loc["T0001"]
    assert t["currency"] == "EUR"
    assert t["net_amount"] == pytest.approx(round(t["quantity"] * t["price"], 2) + t["commission"])
    sale = sample.trades.set_index("trade_id").loc["T0002"]
    assert sale["net_amount"] == pytest.approx(round(sale["quantity"] * sale["price"], 2) - sale["commission"])


def test_daily_lookups(sample):
    day = dt.date(2025, 10, 1)
    assert set(sample.fx_on(day)) == {"USD", "GBP", "CHF"}
    assert len(sample.prices_on(day)) == 15
    assert sample.custodian_cash_on(dt.date(2025, 10, 4)) is None  # a Saturday


def test_amended_confirm_replaces_the_original(sample):
    first = sample.live_confirms(dt.date(2025, 10, 9)).set_index("client_ref").loc["T0003"]
    later = sample.live_confirms(dt.date(2025, 10, 13)).set_index("client_ref").loc["T0003"]
    assert first["status"] == "NEW" and later["status"] == "AMEND"
    assert first["price"] != later["price"]


def test_canceled_confirm_drops_out(sample):
    assert "C79001" in set(sample.live_confirms(dt.date(2025, 11, 26))["confirm_id"])
    assert "C79001" not in set(sample.live_confirms(dt.date(2025, 12, 2))["confirm_id"])


def test_ecb_rates():
    rates = parse_ecb_csv(ECB_SAMPLE)
    assert list(rates.columns) == ["date", "currency", "rate"]
    assert rates.iloc[0].tolist() == [dt.date(2025, 10, 1), "GBP", 0.87245]
    assert len(rates) == 3


def test_not_an_ecb_file():
    with pytest.raises(ValueError):
        parse_ecb_csv("date,price\n2025-10-01,1.0\n")


def test_ecb_url():
    url = ecb_url(["usd", "GBP"], dt.date(2025, 10, 1), dt.date(2025, 12, 31))
    assert url.startswith("https://data-api.ecb.europa.eu/service/data/EXR/D.USD+GBP.EUR.SP00.A?")
    assert "startPeriod=2025-10-01" in url and "endPeriod=2025-12-31" in url and "format=csvdata" in url
