"""Tax calculations for Revolut Flexible Account interest income."""

from __future__ import annotations

from decimal import Decimal

from renta.cuentas.models import CuentasSummary, FlexibleFundInterest
from renta.utils.money import round_eur

_ZERO = Decimal("0")


def build_summary(accounts: list[FlexibleFundInterest], tax_year: int) -> CuentasSummary:
    """Aggregate per-fund interest records into a fiscal-year summary."""
    total_gross = sum((a.gross_eur for a in accounts), _ZERO)
    total_fees = sum((a.fees_eur for a in accounts), _ZERO)
    total_tax = sum((a.tax_withheld_eur for a in accounts), _ZERO)
    return CuentasSummary(
        tax_year=tax_year,
        accounts=list(accounts),
        total_gross_eur=round_eur(total_gross),
        total_fees_eur=round_eur(total_fees),
        total_net_eur=round_eur(total_gross - total_fees),
        total_tax_withheld_eur=round_eur(total_tax),
    )
