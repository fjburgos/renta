"""
Tax calculations for ETFs and stocks: FIFO cost basis, wash-sale rule, capital gains/losses.

Public API:
    calculate(path, tax_year) -> str          — report for a single year
    calculate_all_years(path) -> dict[int, str] — reports for every year with sales
"""

from __future__ import annotations

from pathlib import Path

from renta.etfs.fifo import FifoEngine
from renta.etfs.models import CapitalGainEvent, WashSaleRecord
from renta.etfs.parser import parse_degiro_xlsx
from renta.etfs.report import TaxSummary, build_report, build_tax_summary
from renta.etfs.wash_sale import apply_wash_sale_rule


def _run_pipeline(
    path: Path,
) -> tuple[list[CapitalGainEvent], list[WashSaleRecord]]:
    """Parse the XLSX and run FIFO + wash-sale. Returns (events, wash_records)."""
    transactions = parse_degiro_xlsx(path)
    engine = FifoEngine()
    events = engine.process(transactions)
    return apply_wash_sale_rule(events, transactions)


def build_all_summaries(path: Path) -> dict[int, TaxSummary]:
    """
    Full pipeline run once; returns a TaxSummary for every year that has sales.

    Args:
        path: Path to the DeGiro XLSX export file.

    Returns:
        Mapping of tax_year → TaxSummary, ordered chronologically.
        Only years with at least one sale event are included.
    """
    events, wash_records = _run_pipeline(path)
    years = sorted({e.transfer_date.year for e in events})
    return {year: build_tax_summary(events, wash_records, year) for year in years}


def calculate(path: Path, tax_year: int) -> str:
    """
    Full pipeline: parse → FIFO → wash-sale → report for a single year.

    Args:
        path: Path to the DeGiro XLSX export file.
        tax_year: The fiscal year to report on (e.g. 2024).

    Returns:
        A plain-text IRPF report ready to be printed or saved.
    """
    events, wash_records = _run_pipeline(path)
    return build_report(events, wash_records, tax_year)


def calculate_all_years(path: Path) -> dict[int, str]:
    """
    Full pipeline run once; returns one report per year that contains sales.

    Args:
        path: Path to the DeGiro XLSX export file.

    Returns:
        Mapping of tax_year → report string, ordered chronologically.
        Only years with at least one sale event are included.
    """
    events, wash_records = _run_pipeline(path)
    years = sorted({e.transfer_date.year for e in events})
    return {year: build_report(events, wash_records, year) for year in years}
