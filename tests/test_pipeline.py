"""The sample fund end to end: NAV, fees, dealing and reconciliation."""

import datetime as dt

import pandas as pd
import pytest

from fundnav.cli import main
from fundnav.data import SAMPLE_DIR
from fundnav.report import write_outputs


def test_every_day_proves(sample_run):
    assert len(sample_run.days) == 63
    assert all(abs(d.proof) < 0.005 for d in sample_run.days)


def test_opening_balance_sheet_ties(sample_run):
    assert sample_run.opening_balance_sheet["Net assets"] == pytest.approx(180_000_000.00)


def test_year_end_nav_per_share(sample_run):
    navs = {code: v.nav_per_share for code, v in sample_run.last.valuations.items()}
    assert navs == {"A-EUR": 113.6821, "I-EUR": 129.4197, "I-USD": 145.2931}
    assert sample_run.last.net_assets == pytest.approx(189_379_683.66)


def test_performance_fees_crystallize_at_year_end(sample_run):
    last = sample_run.last
    assert last.crystallized == {"I-EUR": 460_299.24, "I-USD": 348_393.55}
    assert last.states["I-EUR"].high_water_mark == 129.4197
    assert last.states["I-USD"].high_water_mark == 145.2931
    assert last.states["I-EUR"].performance_fee_accrued == 0.0


def test_performance_fee_crystallizes_on_redemption(sample_run):
    deals = sample_run.deals().set_index("deal_id")
    assert deals.loc["D0006", "performance_fee_crystallized"] == 5_272.26
    assert deals.loc["D0010", "performance_fee_crystallized"] == 23_705.25
    assert deals.loc["D0001", "performance_fee_crystallized"] == 0.0


def test_dealing(sample_run):
    deals = sample_run.deals().set_index("deal_id")
    assert deals.loc["D0002", "units"] == 20_777.177  # USD 3,000,000 at 144.3892
    assert deals.loc["D0010", "amount"] == 3_250_847.49  # 25,000 units at 130.0339
    assert deals.loc["D0013", "settles"] == dt.date(2026, 1, 5)


def test_breaks_match_expected_breaks(sample_run):
    expected = pd.read_csv(SAMPLE_DIR / "expected_breaks.csv", keep_default_na=False)
    register = sample_run.last.register
    found = sorted(
        (r["key"], str(r["first_seen"]), "" if r["resolved_on"] is None or pd.isna(r["resolved_on"]) else str(r["resolved_on"]))
        for _, r in register.iterrows()
    )
    assert found == sorted(zip(expected["key"], expected["first_seen"], expected["resolved_on"]))
    details = dict(zip(register["key"] + "|" + register["first_seen"].astype(str), register["detail"]))
    for key, first, detail in zip(expected["key"], expected["first_seen"], expected["detail"]):
        assert details[f"{key}|{first}"] == detail


def test_cash_inside_tolerance_is_not_a_break(sample_run):
    assert not (sample_run.last.register["key"] == "CASH|GBP").any()


def test_checks_find_the_stale_price_and_the_big_fall(sample_run):
    checks = sample_run.checks()
    found = {(c.date, c.check) for c in checks.itertuples()}
    assert found == {
        (dt.date(2025, 11, 6), "large price move"),
        (dt.date(2025, 11, 19), "stale price"),
        (dt.date(2025, 11, 20), "stale price"),
    }


def test_outputs(tmp_path, sample_run):
    paths = write_outputs(sample_run, tmp_path, sample=True)
    page = paths["report"].read_text()
    assert "Sample Global Equity Fund" in page and "Synthetic sample data" in page
    assert len(pd.read_csv(paths["nav_history"])) == 63 * 3


def test_command_line(tmp_path):
    assert main(["run", "--sample", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "nav_pack_2025-12-31.html").exists()
    assert main(["run", "--sample", "--out", str(tmp_path), "--fail-on-breaks"]) == 2
