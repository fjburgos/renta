"""
Shared fixtures for dividend tests.

XLSX builder helpers follow the real DeGiro Account.xlsx column layout:
  [0] Fecha  [1] Hora  [2] FechaValor  [3] Producto  [4] ISIN  [5] Descripción
  [6] Tipo   [7] Moneda  [8] Importe  [9] SaldoMoneda  [10] Saldo  [11] IDOrden
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from renta.dividends.ecb import FxRatesProvider
from renta.utils.exceptions import FxRateUnavailableError


# ── XLSX builder ──────────────────────────────────────────────────────────────

_HEADER = [
    "Fecha", "Hora", "Fecha valor", "Producto", "ISIN", "Descripción",
    "Tipo", "Variación", None, "Saldo", None, "ID Orden",
]


def _row(
    fecha: str,
    hora: str,
    fecha_valor: str,
    producto: str | None,
    isin: str | None,
    descripcion: str,
    tipo: float | None,
    moneda: str | None,
    importe: float | None,
    saldo_moneda: str = "EUR",
    saldo: float = 0.0,
    id_orden: str | None = None,
) -> list[Any]:
    return [fecha, hora, fecha_valor, producto, isin, descripcion,
            tipo, moneda, importe, saldo_moneda, saldo, id_orden]


def build_xlsx(tmp_path: Path, rows: list[list[Any]], name: str = "Account.xlsx") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estado de cuenta"  # type: ignore[union-attr]
    ws.append(_HEADER)  # type: ignore[union-attr]
    for r in rows:
        ws.append(r)  # type: ignore[union-attr]
    path = tmp_path / name
    wb.save(path)
    return path


# ── Standard row factories ────────────────────────────────────────────────────

def dividendo(fecha: str, isin: str, ticker: str, moneda: str, importe: float,
               fecha_valor: str | None = None) -> list[Any]:
    return _row(fecha, "07:00", fecha_valor or _prev_day(fecha), ticker, isin,
                "Dividendo", None, moneda, importe)


def retencion(fecha: str, isin: str, ticker: str, moneda: str, importe: float,
              fecha_valor: str | None = None) -> list[Any]:
    return _row(fecha, "07:00", fecha_valor or _prev_day(fecha), ticker, isin,
                "Retención del dividendo", None, moneda, importe)


def retirada(fecha: str, fecha_valor: str, moneda: str, importe: float, tipo: float,
             hora: str = "07:00") -> list[Any]:
    return _row(fecha, hora, fecha_valor, None, None, "Retirada Cambio de Divisa",
                tipo, moneda, importe)


def ingreso(fecha: str, fecha_valor: str, eur_amount: float, hora: str = "07:00") -> list[Any]:
    return _row(fecha, hora, fecha_valor, None, None, "Ingreso Cambio de Divisa",
                None, "EUR", eur_amount)


def _prev_day(fecha: str) -> str:
    d = datetime.datetime.strptime(fecha, "%d-%m-%Y").date()
    return (d - datetime.timedelta(days=1)).strftime("%d-%m-%Y")


# ── Fake ECB provider ─────────────────────────────────────────────────────────

class FakeECB:
    """Returns predetermined rates; raises if a rate was not registered."""

    def __init__(self, rates: dict[tuple[str, datetime.date], Decimal] | None = None) -> None:
        self._rates: dict[tuple[str, datetime.date], Decimal] = rates or {}

    def get_rate(self, currency: str, on_date: datetime.date) -> Decimal:
        key = (currency, on_date)
        if key in self._rates:
            return self._rates[key]
        raise FxRateUnavailableError(f"FakeECB: no rate for {currency} on {on_date}")

    def with_rate(self, currency: str, on_date: datetime.date, rate: Decimal) -> "FakeECB":
        return FakeECB({**self._rates, (currency, on_date): rate})


class NeverCalledECB:
    """Raises immediately if called — use to assert ECB is NOT used in a test."""

    def get_rate(self, currency: str, on_date: datetime.date) -> Decimal:
        raise AssertionError(f"ECB provider should not have been called (currency={currency}, date={on_date})")


# ── Type alias ────────────────────────────────────────────────────────────────

ECBProvider = FxRatesProvider
