"""
Parser for DeGiro XLSX transaction exports.

Column positions are fixed by the DeGiro format (some columns have no header):
  0  Fecha (DD-MM-YYYY)
  1  Hora
  2  Producto
  3  ISIN
  4  Bolsa de referencia
  5  Centro de ejecución
  6  Número          (positive = purchase, negative = sale)
  7  Precio
  8  (price currency)
  9  Valor local
  10 (local currency)
  11 Valor EUR
  12 Tipo de cambio  (None for EUR transactions)
  13 Comisión AutoFX
  14 Costes de transacción y/o externos EUR  (may be None)
  15 Total EUR       (negative = purchase outflow, positive = sale inflow)
  16 ID Orden
  17 (unnamed)
  18 (unnamed)
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from pathlib import Path
import warnings

import openpyxl

from renta.etfs.models import RawTransaction, Transaction
from renta.utils.exceptions import ParseError
from renta.utils.money import to_decimal, to_decimal_or_zero

# Column indices
_COL_DATE = 0
_COL_TIME = 1
_COL_PRODUCT = 2
_COL_ISIN = 3
_COL_EXCHANGE = 4
_COL_VENUE = 5
_COL_QUANTITY = 6
_COL_PRICE = 7
_COL_PRICE_CURRENCY = 8
_COL_LOCAL_VALUE = 9
_COL_LOCAL_CURRENCY = 10
_COL_EUR_VALUE = 11
_COL_FX_RATE = 12
_COL_AUTOFX_COMMISSION = 13
_COL_TRANSACTION_COSTS = 14
_COL_TOTAL_EUR = 15
_COL_ORDER_ID = 17  # col 16 is blank in DeGiro exports; UUID is at col 17

_MIN_COLUMNS = 18  # need at least up to col 17 (order_id)


def parse_degiro_xlsx(path: Path) -> list[Transaction]:
    """
    Parse a DeGiro XLSX export and return consolidated transactions sorted by date.

    Split executions (same order_id + same date) are merged into a single Transaction.
    """
    # Note: read_only=True is incompatible with some DeGiro exports (missing default style).
    # data_only=True ensures formula cells return their cached value instead of the formula.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style", category=UserWarning)
        wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    if ws is None:
        raise ParseError(f"No active sheet found in {path}")

    raw_rows: list[RawTransaction] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header
        if not row or row[_COL_DATE] is None:
            continue  # skip empty rows
        try:
            raw_rows.append(_parse_raw_row(row))
        except ParseError as exc:
            raise ParseError(f"Row {i + 1}: {exc}") from exc

    wb.close()
    transactions = _merge_executions(raw_rows)
    return sorted(transactions, key=lambda t: t.date)


def _parse_raw_row(row: tuple) -> RawTransaction:  # type: ignore[type-arg]
    if len(row) < _MIN_COLUMNS:
        raise ParseError(f"Expected at least {_MIN_COLUMNS} columns, got {len(row)}")

    date_str = row[_COL_DATE]
    if not isinstance(date_str, str):
        raise ParseError(f"Date must be a string in DD-MM-YYYY format, got {date_str!r}")

    try:
        parsed_date = datetime.datetime.strptime(date_str, "%d-%m-%Y").date()
    except ValueError as exc:
        raise ParseError(f"Cannot parse date {date_str!r}: {exc}") from exc

    isin = row[_COL_ISIN]
    if not isin:
        raise ParseError("ISIN is empty")

    quantity_raw = row[_COL_QUANTITY]
    if quantity_raw is None or quantity_raw == 0:
        raise ParseError(f"Quantity is None or zero for ISIN {isin}")

    order_id = row[_COL_ORDER_ID]
    if not order_id:
        raise ParseError(f"Order ID is empty for ISIN {isin}")

    fx_rate_raw = row[_COL_FX_RATE]
    fx_rate = to_decimal(fx_rate_raw) if fx_rate_raw is not None else None

    return RawTransaction(
        date=parsed_date,
        time=str(row[_COL_TIME] or ""),
        product=str(row[_COL_PRODUCT] or ""),
        isin=str(isin),
        exchange=str(row[_COL_EXCHANGE] or ""),
        execution_venue=str(row[_COL_VENUE] or ""),
        quantity=to_decimal(quantity_raw),
        price=to_decimal_or_zero(row[_COL_PRICE]),
        price_currency=str(row[_COL_PRICE_CURRENCY] or "EUR"),
        local_value=to_decimal_or_zero(row[_COL_LOCAL_VALUE]),
        local_currency=str(row[_COL_LOCAL_CURRENCY] or "EUR"),
        eur_value=to_decimal_or_zero(row[_COL_EUR_VALUE]),
        fx_rate=fx_rate,
        autofx_commission=to_decimal_or_zero(row[_COL_AUTOFX_COMMISSION]),
        transaction_costs_eur=to_decimal_or_zero(row[_COL_TRANSACTION_COSTS]),
        total_eur=to_decimal(row[_COL_TOTAL_EUR]),
        order_id=str(order_id),
    )


def _merge_executions(raws: list[RawTransaction]) -> list[Transaction]:
    """
    Group RawTransactions by (order_id, date) and sum their amounts.
    Rationale: DeGiro may route a single order through multiple venues on the same day.
    Different dates with the same order_id are kept as separate lots (partial fills on
    different trading days have different acquisition dates for FIFO purposes).
    """
    groups: dict[tuple[str, datetime.date], list[RawTransaction]] = defaultdict(list)
    for raw in raws:
        groups[(raw.order_id, raw.date)].append(raw)

    transactions: list[Transaction] = []
    for (order_id, tx_date), group in groups.items():
        first = group[0]
        total_quantity = sum((r.quantity for r in group), start=first.quantity - first.quantity)
        total_eur = sum((r.total_eur for r in group), start=first.total_eur - first.total_eur)
        total_costs = sum(
            (r.transaction_costs_eur for r in group),
            start=first.transaction_costs_eur - first.transaction_costs_eur,
        )

        # Re-compute sums using Decimal zero to avoid type issues
        from decimal import Decimal

        total_quantity = sum((r.quantity for r in group), Decimal("0"))
        total_eur = sum((r.total_eur for r in group), Decimal("0"))
        total_costs = sum((r.transaction_costs_eur for r in group), Decimal("0"))

        transactions.append(
            Transaction(
                date=tx_date,
                product=first.product,
                isin=first.isin,
                quantity=total_quantity,
                total_eur=total_eur,
                transaction_costs_eur=total_costs,
                order_id=order_id,
            )
        )

    return transactions
