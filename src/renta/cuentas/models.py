from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class FlexibleFundInterest:
    """Interest income from a single Revolut Flexible Account (Cartera Flexible).

    Amounts in native currency and their EUR equivalents as reported by Revolut.
    When has_eur_equivalent is False (old v1 CSV format for non-EUR funds), the
    _eur fields are zero and the native amounts must be converted manually.
    """

    isin: str
    fund_name: str
    currency: str  # native currency code: "EUR", "GBP", etc.
    gross_native: Decimal  # interés bruto in native currency
    fees_native: Decimal  # comisiones de servicio in native currency
    tax_withheld_native: Decimal  # impuestos retenidos in native currency
    gross_eur: Decimal  # gross_native converted to EUR (from Revolut statement)
    fees_eur: Decimal
    tax_withheld_eur: Decimal
    has_eur_equivalent: bool = True  # False for v1 non-EUR funds (no EUR data in file)


@dataclass
class CuentasSummary:
    """Aggregated interest income for a fiscal year across all Revolut Flexible Accounts."""

    tax_year: int
    accounts: list[FlexibleFundInterest]
    total_gross_eur: Decimal
    total_fees_eur: Decimal
    total_net_eur: Decimal  # gross - fees: amount actually distributed to the account
    total_tax_withheld_eur: Decimal
