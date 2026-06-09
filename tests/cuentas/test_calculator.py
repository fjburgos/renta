"""Tests for the cuentas calculator."""

from __future__ import annotations

from decimal import Decimal

from renta.cuentas.calculator import build_summary
from renta.cuentas.models import FlexibleFundInterest

_D = Decimal


def _fund(
    isin: str = "IE000AZVL3K0",
    currency: str = "EUR",
    gross_eur: str = "0.00",
    fees_eur: str = "0.00",
    tax_eur: str = "0.00",
) -> FlexibleFundInterest:
    g = _D(gross_eur)
    f = _D(fees_eur)
    t = _D(tax_eur)
    return FlexibleFundInterest(
        isin=isin,
        fund_name=f"Fund {currency}",
        currency=currency,
        gross_native=g,
        fees_native=f,
        tax_withheld_native=t,
        gross_eur=g,
        fees_eur=f,
        tax_withheld_eur=t,
    )


def test_empty_accounts() -> None:
    s = build_summary([], 2025)
    assert s.tax_year == 2025
    assert s.total_gross_eur == _D("0.00")
    assert s.total_fees_eur == _D("0.00")
    assert s.total_net_eur == _D("0.00")
    assert s.total_tax_withheld_eur == _D("0.00")


def test_single_eur_fund() -> None:
    f = _fund(gross_eur="93.69", fees_eur="34.73")
    s = build_summary([f], 2025)
    assert s.total_gross_eur == _D("93.69")
    assert s.total_fees_eur == _D("34.73")
    assert s.total_net_eur == _D("58.96")
    assert s.total_tax_withheld_eur == _D("0.00")


def test_eur_and_gbp_funds() -> None:
    eur = _fund(isin="IE000AZVL3K0", currency="EUR", gross_eur="93.69", fees_eur="34.73")
    gbp = _fund(isin="IE0002RUHW32", currency="GBP", gross_eur="173.15", fees_eur="50.57")
    s = build_summary([eur, gbp], 2025)
    assert s.total_gross_eur == _D("266.84")
    assert s.total_fees_eur == _D("85.30")
    assert s.total_net_eur == _D("181.54")
    assert len(s.accounts) == 2


def test_rounding() -> None:
    # Gross - fees should round to 2 decimal places
    f = _fund(gross_eur="10.005", fees_eur="0.002")
    s = build_summary([f], 2025)
    # 10.005 - 0.002 = 10.003 → rounds to 10.00 (ROUND_HALF_UP)
    assert s.total_net_eur == _D("10.00")
