"""Tests for the Revolut CSV parser."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from renta.cuentas.parser import parse_revolut_csv, _parse_eur, _parse_native, _parse_decimal
from renta.utils.exceptions import ParseError

# ── Minimal fixture CSV ───────────────────────────────────────────────────────

_EUR_FUND_SUMMARY = """\
"Fondos Monetarios Flexibles Resúmenes",,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles  (EUR)",,,,,,,
,,,,,,,
"Interés obtenido",,,,,,,
"Interés bruto","93,69€","Comisiones de servicio","34,73€",,,,
"Impuestos retenidos","0,00€","Interés neto","58,96€",,,,
,,,,,,,
"Datos de los Fondos Monetarios Flexibles",,,,,,,
"Modalidades de participaciones",Particular,,,,,,
,,,,,,,
"Información del fondo",,,,,,,
"Fondo paraguas","Fidelity Institutional Liquidity Fund PLC","Divisa base",euro,,,,
"Añadir dinero","The Euro Fund","Management company","FIL Investment Management",,,,
"Clase de participación en el fondo","Class R Flex Distributing Shares",,,,,,
"Código ISIN del fondo",IE000AZVL3K0,,,,,,
"Tipo de fondo","LVNAV",,,,,,
,,,,,,,
---------,,,,,,,
,,,,,,,
---------,,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles Estado de transacciones",,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles  (EUR)",,,,,,,
,,,,,,,
"Extracto de transacción",,,,,,,
Fecha,Descripción,"Interés neto","Impuestos retenidos","Otros impuestos","Comisiones de servicio","Intereses netos distribuidos y retirados",
"1 ene 2025","Interest earned - Cartera Flexible","0,18€","0,00€","0,00€","0,05€","0,13€",
"2 ene 2025","Interest earned - Cartera Flexible","0,17€","0,00€","0,00€","0,05€","0,12€",
"""

_EUR_GBP_FUND_SUMMARY = """\
"Fondos Monetarios Flexibles Resúmenes",,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles  (EUR)",,,,,,,
,,,,,,,
"Interés obtenido",,,,,,,
"Interés bruto","93,69€","Comisiones de servicio","34,73€",,,,
"Impuestos retenidos","0,00€","Interés neto","58,96€",,,,
,,,,,,,
"Información del fondo",,,,,,,
"Añadir dinero","The Euro Fund",,,,,,
"Código ISIN del fondo",IE000AZVL3K0,,,,,,
,,,,,,,
---------,,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles  (GBP)",,,,,,,
,,,,,,,
"Interés obtenido",,,,,,,
"Interés bruto","148,42£ (173,15€)","Comisiones de servicio","43,27£ (50,57€)",,,,
"Impuestos retenidos","0,00£ (0,00€)","Interés neto","105,15£ (122,58€)",,,,
,,,,,,,
"Información del fondo",,,,,,,
"Añadir dinero","The Sterling Fund",,,,,,
"Código ISIN del fondo",IE0002RUHW32,,,,,,
,,,,,,,
---------,,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles Estado de transacciones",,,,,,,
,,,,,,,
"Fondos Monetarios Flexibles  (EUR)",,,,,,,
,,,,,,,
Fecha,Descripción,"Interés neto",,,,,,
"15 mar 2025","Interest earned - Cartera Flexible","0,60€",,,,,,
"""


def _write_csv(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "statement.csv"
    p.write_text(content, encoding="utf-8")
    return p


# ── parse_revolut_csv ─────────────────────────────────────────────────────────


def test_parse_single_eur_fund(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, _EUR_FUND_SUMMARY)
    funds, year = parse_revolut_csv(path)

    assert year == 2025
    assert len(funds) == 1
    f = funds[0]
    assert f.isin == "IE000AZVL3K0"
    assert f.fund_name == "The Euro Fund"
    assert f.currency == "EUR"
    assert f.gross_eur == Decimal("93.69")
    assert f.fees_eur == Decimal("34.73")
    assert f.tax_withheld_eur == Decimal("0.00")
    assert f.gross_native == Decimal("93.69")


def test_parse_eur_and_gbp_funds(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, _EUR_GBP_FUND_SUMMARY)
    funds, year = parse_revolut_csv(path)

    assert year == 2025
    assert len(funds) == 2

    eur = next(f for f in funds if f.currency == "EUR")
    gbp = next(f for f in funds if f.currency == "GBP")

    assert eur.isin == "IE000AZVL3K0"
    assert eur.gross_eur == Decimal("93.69")
    assert eur.fees_eur == Decimal("34.73")

    assert gbp.isin == "IE0002RUHW32"
    assert gbp.fund_name == "The Sterling Fund"
    assert gbp.gross_eur == Decimal("173.15")
    assert gbp.fees_eur == Decimal("50.57")
    assert gbp.tax_withheld_eur == Decimal("0.00")
    assert gbp.gross_native == Decimal("148.42")
    assert gbp.fees_native == Decimal("43.27")


def test_missing_year_raises(tmp_path: Path) -> None:
    # No transaction rows → cannot determine year
    content = """\
"Fondos Monetarios Flexibles Resúmenes",,,
"Fondos Monetarios Flexibles Estado de transacciones",,,
"""
    path = _write_csv(tmp_path, content)
    with pytest.raises(ParseError, match="tax year"):
        parse_revolut_csv(path)


# ── Amount parsing helpers ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "s,expected",
    [
        ("93,69€", Decimal("93.69")),
        ("0,00€", Decimal("0.00")),
        ("1.234,56€", Decimal("1234.56")),
        ("148,42£ (173,15€)", Decimal("173.15")),
        ("43,27£ (50,57€)", Decimal("50.57")),
        ("0,00£ (0,00€)", Decimal("0.00")),
    ],
)
def test_parse_eur(s: str, expected: Decimal) -> None:
    assert _parse_eur(s) == expected


@pytest.mark.parametrize(
    "s,expected",
    [
        ("93,69€", Decimal("93.69")),
        ("148,42£ (173,15€)", Decimal("148.42")),
        ("43,27£ (50,57€)", Decimal("43.27")),
        ("0,00£ (0,00€)", Decimal("0.00")),
    ],
)
def test_parse_native(s: str, expected: Decimal) -> None:
    assert _parse_native(s) == expected


@pytest.mark.parametrize(
    "s,expected",
    [
        ("93.69", Decimal("93.69")),
        ("93,69", Decimal("93.69")),
        ("1.234,56", Decimal("1234.56")),
        ("0", Decimal("0")),
    ],
)
def test_parse_decimal(s: str, expected: Decimal) -> None:
    assert _parse_decimal(s) == expected


def test_parse_eur_invalid_raises() -> None:
    with pytest.raises(ParseError):
        _parse_eur("no-amount-here")


# ── v1 format fixtures ────────────────────────────────────────────────────────

_V1_EUR_ONLY = """\
"Summary for Flexible Cash Funds - EUR"
"Interés total obtenido","€119.4882"
"Comisión total","€25.1234"
"Impuestos totales","€0.0000"
"Transactions for Flexible Cash Funds - EUR"
"31 dic 2024 1:54:46","Interest PAID EUR Class R IE000AZVL3K0","€1.23"
"30 dic 2024 2:00:00","Interest PAID EUR Class R IE000AZVL3K0","€0.45"
"""

_V1_EUR_AND_GBP = """\
"Summary for Flexible Cash Funds - EUR"
"Interés total obtenido","€119.4882"
"Comisión total","€25.1234"
"Impuestos totales","€0.0000"
"Summary for Flexible Cash Funds - GBP"
"Interés total obtenido","£31.0107"
"Comisión total","£7.7800"
"Impuestos totales","£0.0000"
"Transactions for Flexible Cash Funds - EUR"
"31 dic 2024 1:54:46","Interest PAID EUR Class R IE000AZVL3K0","€1.23"
"Transactions for Flexible Cash Funds - GBP"
"30 dic 2024 3:00:00","Interest PAID GBP Class R IE0002RUHW32","£0.50"
"""


# ── v1 parser tests ───────────────────────────────────────────────────────────


def test_v1_format_raises_parse_error(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, _V1_EUR_ONLY)
    with pytest.raises(ParseError, match="legacy v1 format"):
        parse_revolut_csv(path)


def test_v1_gbp_format_raises_parse_error(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, _V1_EUR_AND_GBP)
    with pytest.raises(ParseError, match="legacy v1 format"):
        parse_revolut_csv(path)
