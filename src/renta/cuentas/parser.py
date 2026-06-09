"""Parser for Revolut consolidated statement CSV (Extracto consolidado).

Only the v2 format is supported: "consolidated-statement-v2_..." — section-based
with EUR equivalents for all currencies.

The legacy v1 format ("consolidated-statement_..." without the -v2 suffix) can be
re-downloaded from Revolut in v2 format: Profile → Documents & statements →
Custom statement → Excel → Tax year → Generate.
"""

from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from renta.cuentas.models import FlexibleFundInterest
from renta.utils.exceptions import ParseError

# ── v2 patterns ───────────────────────────────────────────────────────────────

# "Fondos Monetarios Flexibles  (EUR)" / "Fondos Monetarios Flexibles  (GBP)"
_V2_FUND_HEADER_RE = re.compile(r"^Fondos Monetarios Flexibles\s+\((\w+)\)$")

_V2_SUMMARY_SECTION = "Fondos Monetarios Flexibles Resúmenes"
_V2_TRANSACTIONS_SECTION = "Fondos Monetarios Flexibles Estado de transacciones"

# v1 detection: first non-empty row of a legacy file starts with this
_V1_FUND_HEADER_RE = re.compile(r"^Summary for Flexible Cash Funds - \w+$")

# Spanish date with optional time: "1 ene 2025" or "31 dic 2024 1:54:46"
_DATE_YEAR_RE = re.compile(r"^\d{1,2} \w{3} (\d{4})")

_CURRENCY_SYMBOL: dict[str, str] = {"EUR": "€", "GBP": "£", "USD": "$"}


# ── public API ────────────────────────────────────────────────────────────────


def parse_revolut_csv(path: Path) -> tuple[list[FlexibleFundInterest], int]:
    """Parse a Revolut consolidated statement CSV (v2 format only).

    Returns a list of FlexibleFundInterest records and the tax year inferred
    from transaction dates in the file.

    Raises ParseError if the file is in the legacy v1 format, cannot be parsed,
    or the year cannot be determined.
    """
    rows = _read_csv(path)
    if _is_v1_format(rows):
        raise ParseError(
            f"{path.name} is in the legacy v1 format, which is not supported. "
            "Re-download from Revolut in v2 format: "
            "Profile → Documents & statements → Custom statement → Excel → Tax year → Generate."
        )
    year = _extract_year_v2(rows)
    funds = _extract_fund_summaries_v2(rows)

    if year is None:
        raise ParseError(
            f"Cannot determine tax year from {path.name}. "
            "Check that the file contains transaction rows with dates."
        )
    return funds, year


# ── CSV reading ───────────────────────────────────────────────────────────────


def _read_csv(path: Path) -> list[list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open(encoding=encoding, newline="") as f:
                return [row for row in csv.reader(f)]
        except UnicodeDecodeError:
            continue
    raise ParseError(f"Cannot decode {path.name}: tried utf-8-sig, utf-8, latin-1")


def _is_v1_format(rows: list[list[str]]) -> bool:
    for row in rows:
        if row and row[0] and row[0].strip():
            return bool(_V1_FUND_HEADER_RE.match(row[0].strip()))
    return False


# ── v2 parser ─────────────────────────────────────────────────────────────────


def _extract_year_v2(rows: list[list[str]]) -> int | None:
    for row in rows:
        if row and row[0]:
            m = _DATE_YEAR_RE.match(row[0].strip())
            if m:
                return int(m.group(1))
    return None


def _extract_fund_summaries_v2(rows: list[list[str]]) -> list[FlexibleFundInterest]:
    summary_start, summary_end = _find_section_bounds(
        rows, _V2_SUMMARY_SECTION, _V2_TRANSACTIONS_SECTION
    )
    summary_rows = rows[summary_start:summary_end]

    fund_starts: list[tuple[int, str]] = []
    for i, row in enumerate(summary_rows):
        currency = _match_v2_fund_header(row)
        if currency is not None:
            fund_starts.append((i, currency))

    results: list[FlexibleFundInterest] = []
    for j, (start_idx, currency) in enumerate(fund_starts):
        next_idx = fund_starts[j + 1][0] if j + 1 < len(fund_starts) else len(summary_rows)
        block = summary_rows[start_idx:next_idx]
        fund = _parse_v2_fund_block(block, currency)
        if fund is not None:
            results.append(fund)

    return results


def _find_section_bounds(
    rows: list[list[str]], start_marker: str, end_marker: str
) -> tuple[int, int]:
    start = 0
    end = len(rows)
    for i, row in enumerate(rows):
        cell = row[0].strip() if row and row[0] else ""
        if cell == start_marker:
            start = i
        elif cell == end_marker and i > start:
            end = i
            break
    return start, end


def _match_v2_fund_header(row: list[str]) -> str | None:
    if not row or not row[0]:
        return None
    m = _V2_FUND_HEADER_RE.match(row[0].strip())
    return m.group(1) if m else None


def _parse_v2_fund_block(block: list[list[str]], currency: str) -> FlexibleFundInterest | None:
    data: dict[str, str] = {}
    for row in block:
        if not row or not row[0]:
            continue
        label = row[0].strip()
        if label == "Interés bruto":
            data["gross"] = row[1].strip() if len(row) > 1 else ""
            data["fees"] = row[3].strip() if len(row) > 3 else ""
        elif label == "Impuestos retenidos":
            data["withholding"] = row[1].strip() if len(row) > 1 else ""
        elif label == "Código ISIN del fondo":
            data["isin"] = row[1].strip() if len(row) > 1 else ""
        elif label == "Añadir dinero":
            data["fund_name"] = row[1].strip() if len(row) > 1 else ""

    if not data.get("gross") or not data.get("isin"):
        return None

    zero_str = "0,00€" if currency == "EUR" else f"0,00{_CURRENCY_SYMBOL.get(currency, '')}"

    return FlexibleFundInterest(
        isin=data["isin"],
        fund_name=data.get("fund_name") or f"Cartera Flexible ({currency})",
        currency=currency,
        gross_native=_parse_native(data["gross"]),
        fees_native=_parse_native(data.get("fees") or zero_str),
        tax_withheld_native=_parse_native(data.get("withholding") or zero_str),
        gross_eur=_parse_eur(data["gross"]),
        fees_eur=_parse_eur(data.get("fees") or "0,00€"),
        tax_withheld_eur=_parse_eur(data.get("withholding") or "0,00€"),
        has_eur_equivalent=True,
    )


# ── Amount parsing ────────────────────────────────────────────────────────────


def _parse_eur(s: str) -> Decimal:
    """Extract the EUR value from a v2 Revolut amount string.

    Handles both simple '93,69€' and multi-currency '148,42£ (173,15€)' formats.
    """
    s = s.strip()
    # Multi-currency: EUR equivalent is inside parentheses, e.g. "148,42£ (173,15€)"
    m = re.search(r"\(([0-9.,]+)€", s)
    if m:
        return _parse_decimal(m.group(1))
    # Simple EUR: strip symbol and any non-numeric chars except , and .
    if "€" in s:
        clean = re.sub(r"[^0-9,.]", "", s)
        return _parse_decimal(clean)
    raise ParseError(f"Cannot extract EUR amount from: {s!r}")


def _parse_native(s: str) -> Decimal:
    """Extract the native-currency value (before any parenthetical EUR equivalent)."""
    s = s.strip()
    # Remove parenthetical part: "148,42£ (173,15€)" → "148,42£"
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # Remove currency symbols
    s = re.sub(r"[€£$¥]", "", s).strip()
    return _parse_decimal(s)


def _parse_decimal(s: str) -> Decimal:
    """Parse a Spanish-formatted number: '1.234,56' → Decimal('1234.56')."""
    s = s.strip()
    if "," in s:
        # Spanish format: . = thousands separator, , = decimal separator
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ParseError(f"Cannot parse decimal from: {s!r}") from exc
