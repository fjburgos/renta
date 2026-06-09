"""
Tax calculations for dividends: rendimientos del capital mobiliario.

Public API:
    calculate(path, tax_year, ...)           → plain-text IRPF report
    calculate_all_years(path, ...)           → dict of year → report for all years with data
    build_summary(path, tax_year, ...)       → DividendSummary for programmatic access
    build_all_summaries(path, ...)           → dict of year → DividendSummary for all years
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

from renta.dividends.calculator import build_summary as _calc_summary
from renta.dividends.ecb import ECBRatesProvider, FxRatesProvider
from renta.dividends.models import DividendSummary
from renta.dividends.parser import parse_account_xlsx
from renta.dividends.report import build_report


def build_summary(
    path: Path,
    tax_year: int,
    fx_overrides: dict[tuple[str, datetime.date], Decimal] | None = None,
    ecb_provider: FxRatesProvider | None = None,
) -> DividendSummary:
    """Parse Account XLSX and return a DividendSummary for the given fiscal year."""
    groups, fx_conversions = parse_account_xlsx(path)
    ecb = ecb_provider if ecb_provider is not None else ECBRatesProvider()
    return _calc_summary(
        groups=groups,
        fx_conversions=fx_conversions,
        tax_year=tax_year,
        ecb=ecb,
        fx_overrides=fx_overrides or {},
    )


def calculate(
    path: Path,
    tax_year: int,
    fx_overrides: dict[tuple[str, datetime.date], Decimal] | None = None,
    ecb_provider: FxRatesProvider | None = None,
) -> str:
    """Full pipeline: parse → FX resolution → report for a single fiscal year."""
    summary = build_summary(path, tax_year, fx_overrides=fx_overrides, ecb_provider=ecb_provider)
    return build_report(summary)


def build_all_summaries(
    path: Path,
    fx_overrides: dict[tuple[str, datetime.date], Decimal] | None = None,
    ecb_provider: FxRatesProvider | None = None,
) -> dict[int, DividendSummary]:
    """Parse once; return a DividendSummary for every year with dividend data."""
    groups, fx_conversions = parse_account_xlsx(path)
    years = sorted({g.date.year for g in groups})
    ecb = ecb_provider if ecb_provider is not None else ECBRatesProvider()
    overrides = fx_overrides or {}
    return {
        year: _calc_summary(
            groups=groups,
            fx_conversions=fx_conversions,
            tax_year=year,
            ecb=ecb,
            fx_overrides=overrides,
        )
        for year in years
    }


def calculate_all_years(
    path: Path,
    fx_overrides: dict[tuple[str, datetime.date], Decimal] | None = None,
    ecb_provider: FxRatesProvider | None = None,
) -> dict[int, str]:
    """Parse once; return one report per year that contains dividend data."""
    groups, fx_conversions = parse_account_xlsx(path)
    years = sorted({g.date.year for g in groups})
    ecb = ecb_provider if ecb_provider is not None else ECBRatesProvider()
    overrides = fx_overrides or {}
    result: dict[int, str] = {}
    for year in years:
        summary = _calc_summary(
            groups=groups,
            fx_conversions=fx_conversions,
            tax_year=year,
            ecb=ecb,
            fx_overrides=overrides,
        )
        result[year] = build_report(summary)
    return result
