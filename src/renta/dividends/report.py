from __future__ import annotations

import datetime
import functools
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import jinja2

from renta.dividends.models import DividendSummary, FxSource

def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(amount: Decimal) -> str:
    return _fmt(amount) + " €"


def _date_fmt(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _ljust(s: object, width: int) -> str:
    return str(s).ljust(width)


def _rjust(s: object, width: int) -> str:
    return str(s).rjust(width)


@functools.cache
def _make_jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    env.filters["fmt"] = _fmt
    env.filters["eur"] = _eur
    env.filters["date_fmt"] = _date_fmt
    env.filters["ljust"] = _ljust
    env.filters["rjust"] = _rjust
    return env


@dataclass(frozen=True)
class CountryTaxEntry:
    country_code: str
    total_gross: Decimal
    total_withholding: Decimal
    total_deductible: Decimal


@dataclass(frozen=True)
class FallbackEntry:
    date: datetime.date
    isin: str
    ticker: str
    original_currency: str
    gross_foreign: Decimal
    fx_rate: Decimal | None
    fx_source: FxSource
    gross_eur: Decimal


def build_report(summary: DividendSummary) -> str:
    country_entries = _build_country_entries(summary)
    fallback_events = _build_fallback_entries(summary)
    irish_isins = sorted({e.isin for e in summary.events if e.irish_etf_note})

    template = _make_jinja_env().get_template("report.txt.j2")
    return template.render(
        tax_year=summary.tax_year,
        events=summary.events,
        total_gross=summary.total_gross,
        total_deductible_foreign_tax=summary.total_deductible_foreign_tax,
        country_entries=country_entries,
        irish_isins=irish_isins,
        fallback_events=fallback_events,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_country_entries(summary: DividendSummary) -> list[CountryTaxEntry]:
    _ZERO = Decimal("0")
    by_country: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    for e in summary.events:
        if e.foreign_withholding == _ZERO:
            continue
        country = e.isin[:2]
        g, w, d = by_country.get(country, (_ZERO, _ZERO, _ZERO))
        by_country[country] = (g + e.gross_amount, w + e.foreign_withholding, d + e.deductible_foreign_tax)
    return [
        CountryTaxEntry(
            country_code=country,
            total_gross=gross,
            total_withholding=wh,
            total_deductible=deductible,
        )
        for country, (gross, wh, deductible) in sorted(by_country.items())
    ]


def _build_fallback_entries(summary: DividendSummary) -> list[FallbackEntry]:
    _ZERO = Decimal("0")
    result = []
    for e in summary.events:
        if e.fx_source == FxSource.DEGIRO or e.original_currency == "EUR":
            continue
        gross_foreign = (e.gross_amount * e.fx_rate).quantize(Decimal("0.01")) if e.fx_rate else _ZERO
        ticker = (e.ticker[:18] + "..") if len(e.ticker) > 20 else e.ticker
        result.append(
            FallbackEntry(
                date=e.date,
                isin=e.isin,
                ticker=ticker,
                original_currency=e.original_currency,
                gross_foreign=gross_foreign,
                fx_rate=e.fx_rate,
                fx_source=e.fx_source,
                gross_eur=e.gross_amount,
            )
        )
    return result
