"""
Parser for the DeGiro Account XLSX (Estado de cuenta).

Column positions — fixed by DeGiro format (some columns have no header):
  0  Fecha           DD-MM-YYYY string
  1  Hora            HH:MM string
  2  Fecha valor     DD-MM-YYYY string
  3  Producto        product name or None
  4  ISIN            or None for non-security movements
  5  Descripción     movement type (see _DESC_* constants)
  6  Tipo            FX rate (float) for Retirada rows; None otherwise
  7  Variación       currency of the movement (e.g. 'EUR', 'USD')
  8  (no header)     amount of the movement (float); positive = credit, negative = debit
  9  Saldo           currency of running balance
  10 (no header)     running balance amount (float)
  11 ID Orden        UUID or None
"""

from __future__ import annotations

import datetime
import warnings
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import openpyxl

from renta.utils.exceptions import ParseError
from renta.utils.money import to_decimal, to_decimal_or_zero

_COL_FECHA = 0
_COL_HORA = 1
_COL_FECHA_VALOR = 2
_COL_PRODUCTO = 3
_COL_ISIN = 4
_COL_DESCRIPCION = 5
_COL_TIPO = 6
_COL_MONEDA = 7
_COL_IMPORTE = 8

_DESC_DIVIDENDO = "Dividendo"
_DESC_RETENCION = "Retención del dividendo"
_DESC_RETIRADA = "Retirada Cambio de Divisa"
_DESC_INGRESO = "Ingreso Cambio de Divisa"


@dataclass(frozen=True)
class DividendGroup:
    """Parsed dividend event: one Dividendo row + optional Retención row for the same (ISIN, date)."""

    date: datetime.date
    isin: str
    ticker: str
    currency: str
    net_foreign: Decimal       # amount from Dividendo row (positive)
    withholding_foreign: Decimal  # abs(amount from Retención row); 0 if none


@dataclass(frozen=True)
class FxConversion:
    """Paired Retirada + Ingreso (or 2021-style double Retirada) for one dividend FX conversion."""

    fecha_valor: datetime.date  # matches DividendGroup.date for linking
    currency: str               # foreign currency (e.g. 'USD')
    fx_rate: Decimal | None     # from Retirada Tipo column; None = pre-2022 format
    net_foreign: Decimal        # abs(Retirada amount) — equals net_foreign of paired DividendGroup
    net_eur: Decimal | None     # from Ingreso/credit row; None if credit row not found


def parse_account_xlsx(path: Path) -> tuple[list[DividendGroup], list[FxConversion]]:
    """Parse a DeGiro Account XLSX and return dividend groups and FX conversions."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style", category=UserWarning)
        wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    if ws is None:
        raise ParseError(f"No active sheet in {path}")

    raw_rows = [
        row
        for i, row in enumerate(ws.iter_rows(values_only=True))
        if i > 0 and row and row[_COL_DESCRIPCION] is not None
    ]
    wb.close()

    dividend_groups = _build_dividend_groups(raw_rows)
    fx_conversions = _build_fx_conversions(raw_rows)
    return dividend_groups, fx_conversions


def _parse_date(value: object) -> datetime.date:
    if not isinstance(value, str):
        raise ParseError(f"Expected date string DD-MM-YYYY, got {value!r}")
    try:
        return datetime.datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError as exc:
        raise ParseError(f"Cannot parse date {value!r}") from exc


def _build_dividend_groups(rows: list[tuple[object, ...]]) -> list[DividendGroup]:
    # Collect dividend rows keyed by (isin, fecha_str)
    by_key: dict[tuple[str, str], list[tuple[object, ...]]] = defaultdict(list)
    for row in rows:
        desc = row[_COL_DESCRIPCION]
        isin = row[_COL_ISIN]
        if desc in (_DESC_DIVIDENDO, _DESC_RETENCION) and isin:
            fecha_str = str(row[_COL_FECHA])
            by_key[(str(isin), fecha_str)].append(row)

    groups: list[DividendGroup] = []
    for (isin, fecha_str), group_rows in by_key.items():
        dividendo = next((r for r in group_rows if r[_COL_DESCRIPCION] == _DESC_DIVIDENDO), None)
        retencion = next((r for r in group_rows if r[_COL_DESCRIPCION] == _DESC_RETENCION), None)
        if dividendo is None:
            continue
        date_ = _parse_date(dividendo[_COL_FECHA_VALOR])
        ticker = str(dividendo[_COL_PRODUCTO] or "")
        currency = str(dividendo[_COL_MONEDA] or "EUR")
        net_foreign = to_decimal(dividendo[_COL_IMPORTE])
        withholding_foreign = (
            abs(to_decimal(retencion[_COL_IMPORTE])) if retencion is not None else Decimal("0")
        )
        groups.append(
            DividendGroup(
                date=date_,
                isin=isin,
                ticker=ticker,
                currency=currency,
                net_foreign=net_foreign,
                withholding_foreign=withholding_foreign,
            )
        )
    return sorted(groups, key=lambda g: g.date)


def _build_fx_conversions(rows: list[tuple[object, ...]]) -> list[FxConversion]:
    # Collect all FX-related rows with ISIN=None
    retirada_rows: dict[tuple[str, str], tuple[object, ...]] = {}  # (fecha, hora) → row
    ingreso_rows: dict[tuple[str, str], tuple[object, ...]] = {}
    # 2021 compat: Retirada EUR positive rows act as Ingreso
    retirada_eur_credit: dict[tuple[str, str], tuple[object, ...]] = {}

    for row in rows:
        desc = row[_COL_DESCRIPCION]
        isin = row[_COL_ISIN]
        if isin is not None:
            continue
        fecha = str(row[_COL_FECHA])
        hora = str(row[_COL_HORA] or "")
        key = (fecha, hora)
        moneda = str(row[_COL_MONEDA] or "")
        importe_raw = row[_COL_IMPORTE]
        importe = to_decimal_or_zero(importe_raw)

        if desc == _DESC_RETIRADA:
            if moneda == "EUR" and importe >= Decimal("0"):
                # 2021-format: positive EUR Retirada acts as credit
                retirada_eur_credit[key] = row
            else:
                retirada_rows[key] = row
        elif desc == _DESC_INGRESO:
            ingreso_rows[key] = row

    conversions: list[FxConversion] = []
    for key, retirada in retirada_rows.items():
        fecha_valor = _parse_date(retirada[_COL_FECHA_VALOR])
        currency = str(retirada[_COL_MONEDA] or "")
        tipo_raw = retirada[_COL_TIPO]
        fx_rate = to_decimal(tipo_raw) if tipo_raw is not None else None
        net_foreign = abs(to_decimal_or_zero(retirada[_COL_IMPORTE]))

        # Prefer dedicated Ingreso row; fall back to 2021-style EUR credit Retirada
        credit_row = ingreso_rows.get(key) or retirada_eur_credit.get(key)
        net_eur: Decimal | None = None
        if credit_row is not None:
            credit_importe = credit_row[_COL_IMPORTE]
            if credit_importe is not None:
                net_eur = to_decimal_or_zero(credit_importe)

        conversions.append(
            FxConversion(
                fecha_valor=fecha_valor,
                currency=currency,
                fx_rate=fx_rate,
                net_foreign=net_foreign,
                net_eur=net_eur,
            )
        )
    return conversions
