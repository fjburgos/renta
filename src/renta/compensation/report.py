"""Plain-text report for the base imponible del ahorro compensation."""

from __future__ import annotations

import datetime
from decimal import Decimal

from renta.compensation.models import (
    CarryForwardEntry,
    CompensationResult,
    YearlyCompensationResult,
)

_ZERO = Decimal("0")
_W = 68  # report width


def build_report(result: CompensationResult, tax_year: int) -> str:
    """Generate a plain-text compensation report for the requested tax year."""
    yearly = next((r for r in result.yearly_results if r.year == tax_year), None)
    if yearly is None:
        return _no_data_report(tax_year)

    lines: list[str] = []
    _header(lines, tax_year)
    _basket_a_section(lines, yearly)
    _basket_b_section(lines, yearly)
    _pending_section(lines, result.pending_carry_forwards, tax_year)
    _footer(lines)
    return "\n".join(lines)


# ── Section builders ──────────────────────────────────────────────────────────


def _header(lines: list[str], year: int) -> None:
    lines += [
        "═" * _W,
        f"  IRPF {year} — COMPENSACIÓN BASE IMPONIBLE DEL AHORRO",
        "═" * _W,
        f"  Generado: {datetime.date.today().strftime('%d/%m/%Y')}",
        f"  Ejercicio fiscal: {year}",
        "  Normativa: Art. 46, 49 Ley 35/2006 IRPF",
        "",
    ]


def _basket_a_section(lines: list[str], r: YearlyCompensationResult) -> None:
    lines += [
        "─" * _W,
        "  CESTA A — Ganancias y pérdidas patrimoniales (Art. 46.b.1 LIRPF)",
        "─" * _W,
        f"  Resultado del ejercicio:           {_fmt(r.gross_basket_a)}",
    ]

    if r.applied_carry_forwards_a:
        lines.append("  Compensación de ejercicios anteriores (Art. 49.2 LIRPF):")
        for cf in r.applied_carry_forwards_a:
            lines.append(
                f"    · Origen {cf.origin_year} (expira {cf.origin_year + 4}): "
                f"aplicado {_fmt_pos(cf.amount_applied)}"
                + (
                    f"  — queda pendiente {_fmt_pos(cf.amount_remaining)}"
                    if cf.amount_remaining > _ZERO
                    else ""
                )
            )

    if r.cross_b_to_a > _ZERO:
        lines.append(
            f"  Compensación cruzada (cesta B → A, ≤25%):  -{_fmt_pos(r.cross_b_to_a)}"
        )

    if r.cross_a_to_b > _ZERO:
        lines.append(
            f"  Compensación cruzada cedida (A → cesta B):  -{_fmt_pos(r.cross_a_to_b)}"
        )

    if r.expired_carry_forwards:
        expired_a = [cf for cf in r.expired_carry_forwards if cf.basket == "A"]
        if expired_a:
            lines.append("  ⚠ Pérdidas expiradas (no compensadas a tiempo):")
            for cf in expired_a:
                lines.append(f"    · Origen {cf.origin_year}: {_fmt_pos(cf.amount)} €")

    net = r.net_basket_a
    if net >= _ZERO:
        lines.append(f"  Saldo final cesta A (casilla 0380):  {_fmt(net)}")
        lines.append("  Casilla 0390: 0,00 €")
    else:
        lines.append("  Casilla 0380: 0,00 €")
        lines.append(f"  Saldo negativo cesta A (casilla 0390):  {_fmt_pos(abs(net))}")

    lines.append("")


def _basket_b_section(lines: list[str], r: YearlyCompensationResult) -> None:
    lines += [
        "─" * _W,
        "  CESTA B — Rendimientos del capital mobiliario (Art. 46.b.2 LIRPF)",
        "─" * _W,
        f"  Rendimientos brutos del ejercicio:  {_fmt(r.gross_basket_b)}",
    ]

    if r.applied_carry_forwards_b:
        lines.append("  Compensación de ejercicios anteriores (Art. 49.2 LIRPF):")
        for cf in r.applied_carry_forwards_b:
            lines.append(
                f"    · Origen {cf.origin_year} (expira {cf.origin_year + 4}): "
                f"aplicado {_fmt_pos(cf.amount_applied)}"
                + (
                    f"  — queda pendiente {_fmt_pos(cf.amount_remaining)}"
                    if cf.amount_remaining > _ZERO
                    else ""
                )
            )

    if r.cross_a_to_b > _ZERO:
        lines.append(
            f"  Compensación cruzada (cesta A → B, ≤25%):  -{_fmt_pos(r.cross_a_to_b)}"
        )

    if r.cross_b_to_a > _ZERO:
        lines.append(
            f"  Compensación cruzada cedida (B → cesta A):  -{_fmt_pos(r.cross_b_to_a)}"
        )

    if r.expired_carry_forwards:
        expired_b = [cf for cf in r.expired_carry_forwards if cf.basket == "B"]
        if expired_b:
            lines.append("  ⚠ Pérdidas expiradas (no compensadas a tiempo):")
            for cf in expired_b:
                lines.append(f"    · Origen {cf.origin_year}: {_fmt_pos(cf.amount)} €")

    net = r.net_basket_b
    if net >= _ZERO:
        lines.append(f"  Saldo final cesta B (rendimientos netos):  {_fmt(net)}")
    else:
        lines.append(f"  Saldo negativo cesta B:  {_fmt_pos(abs(net))}")

    lines.append("")


def _pending_section(
    lines: list[str], pending: list[CarryForwardEntry], tax_year: int
) -> None:
    pending_after = [cf for cf in pending if cf.origin_year <= tax_year]
    if not pending_after:
        return

    lines += [
        "─" * _W,
        "  PÉRDIDAS PENDIENTES PARA EJERCICIOS FUTUROS (Art. 49.2 LIRPF)",
        "─" * _W,
    ]
    for cf in pending_after:
        lines.append(
            f"  · Cesta {cf.basket} — origen {cf.origin_year}: "
            f"{_fmt_pos(cf.amount)} €  "
            f"(expira en la declaración {cf.expiry_year})"
        )
    lines.append("")


def _footer(lines: list[str]) -> None:
    lines += [
        "─" * _W,
        "  Informe generado por renta",
        "  Este informe es orientativo. Verifica los datos con la AEAT.",
        "─" * _W,
    ]


def _no_data_report(year: int) -> str:
    return (
        f"{'═' * _W}\n"
        f"  IRPF {year} — COMPENSACIÓN BASE IMPONIBLE DEL AHORRO\n"
        f"{'═' * _W}\n"
        f"  Sin datos para el ejercicio {year}.\n"
        f"{'─' * _W}\n"
    )


def _fmt(amount: Decimal) -> str:
    sign = "+" if amount >= _ZERO else "-"
    return f"{sign}{_fmt_pos(abs(amount))}"


def _fmt_pos(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
