"""
Compensation of the base imponible del ahorro across fiscal years.

Applies the rules from Art. 46, 49 Ley 35/2006 IRPF:
  - Basket A: G/P patrimoniales from ETF/stock transfers
  - Basket B: Rendimientos del capital mobiliario (dividends + account interest)
  - Cross-compensation limited to 25% of the receiving basket (Art. 49.1.b)
  - Carry-forward of negative balances for up to four fiscal years (Art. 49.2)

Public API:
    calculate_compensation(summaries) → CompensationResult
    build_report(result, tax_year)    → plain-text report string
"""

from renta.compensation.calculator import calculate_compensation
from renta.compensation.models import (
    CarryForwardEntry,
    CompensationResult,
    YearlyBaseSummary,
    YearlyCompensationResult,
)
from renta.compensation.report import build_report

__all__ = [
    "calculate_compensation",
    "build_report",
    "YearlyBaseSummary",
    "CarryForwardEntry",
    "CompensationResult",
    "YearlyCompensationResult",
]
