from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class FxSource(str, Enum):
    DEGIRO = "degiro"
    ECB = "ecb"
    OVERRIDE = "override"


@dataclass(frozen=True)
class DividendEvent:
    date: date
    isin: str
    ticker: str
    gross_amount: Decimal
    foreign_withholding: Decimal
    deductible_foreign_tax: Decimal
    net_amount: Decimal
    original_currency: str
    fx_rate: Decimal | None
    fx_source: FxSource
    irish_etf_note: bool


@dataclass
class DividendSummary:
    tax_year: int
    events: list[DividendEvent]
    total_gross: Decimal
    total_foreign_withholding: Decimal
    total_deductible_foreign_tax: Decimal
    by_country: dict[str, Decimal]  # ISO country code → total gross_amount EUR
