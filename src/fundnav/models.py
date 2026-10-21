"""Fund setup, share class state and the records passed between modules."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Fund setup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expense:
    """A fund-level expense, shared by every share class.

    Either annual_rate (a share of total NAV per year) or annual_amount (a
    fixed amount per year in base currency) is set, not both.
    """

    name: str
    annual_rate: float | None = None
    annual_amount: float | None = None


@dataclass(frozen=True)
class ShareClass:
    code: str
    currency: str
    management_fee: float  # per year, on the class NAV
    performance_fee: float | None = None  # share of gains above the high-water mark


@dataclass(frozen=True)
class Tolerances:
    cash: float = 5.0  # currency units
    price: float = 0.0001  # relative: 0.0001 is one basis point
    amount: float = 1.0  # currency units, on a trade's net amount


@dataclass(frozen=True)
class FundConfig:
    name: str
    base_currency: str
    share_classes: tuple[ShareClass, ...]
    expenses: tuple[Expense, ...]
    holidays: tuple[dt.date, ...]
    tolerances: Tolerances = Tolerances()
    nav_decimals: int = 4  # NAV per share
    unit_decimals: int = 3  # units issued on subscription
    capital_settlement_days: int = 3  # subscriptions and redemptions settle T+3

    def share_class(self, code: str) -> ShareClass:
        for share_class in self.share_classes:
            if share_class.code == code:
                return share_class
        raise KeyError(f"no share class {code!r}")


# ---------------------------------------------------------------------------
# Share class state
# ---------------------------------------------------------------------------


@dataclass
class ClassState:
    """One share class at the end of a valuation day, after dealing."""

    code: str
    units: float
    nav: float  # base currency
    high_water_mark: float | None = None  # per share, class currency
    performance_fee_accrued: float = 0.0  # base currency, current performance period


@dataclass(frozen=True)
class ClassValuation:
    """One share class valued for one day, before that day's dealing."""

    code: str
    nav_before_fees: float  # base currency
    management_fee: float  # base currency, this day's accrual
    performance_fee_accrued: float  # base currency, cumulative for the period
    performance_fee_change: float  # base currency, this day's change in the accrual
    nav: float  # base currency
    nav_per_share: float  # class currency


@dataclass(frozen=True)
class Deal:
    """Units and money for one subscription or redemption."""

    units: float
    amount: float  # class currency


# ---------------------------------------------------------------------------
# Reconciliation records
# ---------------------------------------------------------------------------

# One row per difference found on a day. `key` identifies the same break
# from one day to the next, for example "CASH|USD" or "TRADE|T0007".
BREAK_COLUMNS = ["key", "category", "reference", "detail", "book", "external", "difference"]

# The break register carries breaks across days.
REGISTER_COLUMNS = [
    "key",
    "category",
    "reference",
    "detail",
    "difference",
    "first_seen",
    "last_seen",
    "age",
    "bucket",
    "status",
    "resolved_on",
]

AGE_BUCKETS = ("0-1", "2-5", "6-10", "over 10")
