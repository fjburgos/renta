"""
Tax calculations for Revolut Flexible Account interest income.

Parses the Revolut consolidated statement CSV (Extracto consolidado) and
generates an IRPF report for the Fondos Monetarios Flexibles (Cartera Flexible).

Public API:
    calculate(path, tax_year)     → plain-text IRPF report
    calculate_all_years(path)     → dict of year → report
    build_summary(path, tax_year) → CuentasSummary for programmatic access
"""

from __future__ import annotations

from pathlib import Path

from renta.cuentas.calculator import build_summary as _calc_summary
from renta.cuentas.models import CuentasSummary
from renta.cuentas.parser import parse_revolut_csv
from renta.cuentas.report import build_report


def build_summary(path: Path, tax_year: int) -> CuentasSummary:
    """Parse Revolut CSV and return a CuentasSummary for the given fiscal year."""
    accounts, _ = parse_revolut_csv(path)
    return _calc_summary(accounts, tax_year)


def calculate(path: Path, tax_year: int) -> str:
    """Full pipeline: parse → aggregate → report for a single fiscal year."""
    summary = build_summary(path, tax_year)
    return build_report(summary)


def calculate_all_years(path: Path) -> dict[int, str]:
    """Parse once; return one report for the year found in the file."""
    accounts, year = parse_revolut_csv(path)
    summary = _calc_summary(accounts, year)
    return {year: build_report(summary)}
