from __future__ import annotations

from decimal import Decimal

from renta.dividends.models import DividendEvent, DividendSummary, FxSource

_SEP_WIDE = "═" * 65
_SEP_THIN = "─" * 65
_ZERO = Decimal("0")


def build_report(summary: DividendSummary) -> str:
    parts: list[str] = []
    parts.append(_header(summary.tax_year))
    parts.append(_main_table(summary))
    parts.append(_irpf_boxes(summary))

    dii_section = _double_taxation_section(summary)
    if dii_section:
        parts.append(dii_section)

    irish_section = _irish_etf_note(summary)
    if irish_section:
        parts.append(irish_section)

    fallback_section = _fallback_section(summary)
    if fallback_section:
        parts.append(fallback_section)

    return "\n".join(parts)


# ── sections ──────────────────────────────────────────────────────────────────


def _header(year: int) -> str:
    return f"\n{_SEP_WIDE}\nDIVIDENDOS — EJERCICIO {year}\n{_SEP_WIDE}"


def _main_table(summary: DividendSummary) -> str:
    lines = [
        "",
        "B1. Rendimientos del capital mobiliario — base imponible del ahorro",
        _SEP_THIN,
        f"  {'Fecha':<12} {'ISIN':<14} {'Valor':<24} {'Bruto EUR':>10} {'Retención EUR':>13}",
        f"  {'─'*12} {'─'*14} {'─'*24} {'─'*10} {'─'*13}",
    ]
    for e in summary.events:
        flag = " ⚠IE" if e.irish_etf_note else ""
        ticker = (e.ticker[:22] + "..") if len(e.ticker) > 24 else e.ticker
        lines.append(
            f"  {e.date}  {e.isin:<14} {ticker:<24} {_eur(e.gross_amount):>10}"
            f" {_eur(e.foreign_withholding):>13}{flag}"
        )
    return "\n".join(lines)


def _irpf_boxes(summary: DividendSummary) -> str:
    return (
        f"\n{_SEP_THIN}\n"
        f"  Casilla 0029 — Ingresos íntegros:        {_eur(summary.total_gross):>10}\n"
        f"  Casilla 0031 — Gastos deducibles:         {'0,00':>10}\n"
        f"  Casilla 0595 — Retenciones (DeGiro = 0):  {'0,00':>10}\n"
        f"\n  ⚠ Los números de casilla pueden variar entre ejercicios. Verificar en el Modelo 100 del año."
    )


def _double_taxation_section(summary: DividendSummary) -> str:
    # Only show countries with actual foreign withholding
    by_country: dict[str, tuple[Decimal, Decimal, Decimal]] = {}  # country → (gross, wh, deductible)
    for e in summary.events:
        if e.foreign_withholding == _ZERO:
            continue
        country = e.isin[:2]
        g, w, d = by_country.get(country, (_ZERO, _ZERO, _ZERO))
        by_country[country] = (g + e.gross_amount, w + e.foreign_withholding, d + e.deductible_foreign_tax)

    if not by_country:
        return ""

    lines = [
        f"\n{_SEP_THIN}",
        "I. Deducción por doble imposición internacional (Art. 80 LIRPF)",
        _SEP_THIN,
        f"  {'País':<6} {'Ingresos íntegros':>18} {'Impuesto extranjero':>20} {'Deducible':>10}",
        f"  {'─'*6} {'─'*18} {'─'*20} {'─'*10}",
    ]
    for country, (gross, wh, deductible) in sorted(by_country.items()):
        lines.append(
            f"  {country:<6} {_eur(gross):>18} {_eur(wh):>20} {_eur(deductible):>10}"
        )
    lines.append(
        f"\n  Casilla 0588 — Deducción DII: {_eur(summary.total_deductible_foreign_tax):>10}"
    )
    lines.append(
        "  ⚠ Los números de casilla pueden variar entre ejercicios. Verificar en el Modelo 100 del año."
    )
    return "\n".join(lines)


def _irish_etf_note(summary: DividendSummary) -> str:
    irish = [e for e in summary.events if e.irish_etf_note]
    if not irish:
        return ""
    isins = sorted({e.isin for e in irish})
    lines = [
        f"\n{_SEP_THIN}",
        "⚠  NOTA: ETFs UCITS domiciliados en Irlanda (ISIN IE...)",
        _SEP_THIN,
        "  Los dividendos de ETFs con ISIN IE se declaran íntegramente como rendimiento",
        "  del capital mobiliario con retención extranjera = 0 y sin deducción DII.",
        "  El WHT que el fondo paga internamente sobre dividendos de subyacente USA (15%)",
        "  se absorbe en el NAV/distribución y NO es recuperable por el inversor español.",
        "",
        "  ISINs afectados:",
    ]
    for isin in isins:
        lines.append(f"    • {isin}")
    return "\n".join(lines)


def _fallback_section(summary: DividendSummary) -> str:
    fallback = [e for e in summary.events if e.fx_source != FxSource.DEGIRO and e.original_currency != "EUR"]
    if not fallback:
        return ""

    lines = [
        f"\n{_SEP_WIDE}",
        f"CONVERSIONES FX — MODO FALLBACK ({len(fallback)} evento{'s' if len(fallback) != 1 else ''})",
        _SEP_WIDE,
        "",
        "  Los siguientes dividendos no tenían en el extracto de cuenta las filas",
        "  de conversión automática que DeGiro genera normalmente:",
        "",
        "    Patrón esperado (día hábil siguiente al dividendo, ISIN vacío):",
        '    • "Retirada Cambio de Divisa": importe negativo en divisa original,',
        "       tipo de cambio en columna Tipo (pos. 6), FechaValor = Fecha del dividendo.",
        '    • "Ingreso Cambio de Divisa":  mismo (Fecha, Hora) que la Retirada,',
        "       importe positivo en EUR.",
        "",
        "  Causa más probable: el extracto no cubre el día posterior al último dividendo.",
        "  Exportar con rango +1 día puede hacer desaparecer esta sección.",
        "",
        f"  {'Fecha':<12} {'ISIN':<14} {'Valor':<20} {'Divisa':<6} {'Bruto div.':>10}"
        f" {'FX':>8} {'Fuente':<9} {'Bruto EUR':>10}",
        f"  {'─'*12} {'─'*14} {'─'*20} {'─'*6} {'─'*10} {'─'*8} {'─'*9} {'─'*10}",
    ]
    for e in fallback:
        gross_foreign = (e.gross_amount * e.fx_rate).quantize(Decimal("0.01")) if e.fx_rate else Decimal("0")
        fx_str = str(e.fx_rate) if e.fx_rate else "—"
        source_str = f"[{e.fx_source.value.upper()}]"
        ticker = (e.ticker[:18] + "..") if len(e.ticker) > 20 else e.ticker
        lines.append(
            f"  {e.date}  {e.isin:<14} {ticker:<20} {e.original_currency:<6}"
            f" {_eur(gross_foreign):>10} {fx_str:>8} {source_str:<9} {_eur(e.gross_amount):>10}"
        )
    lines.append(_SEP_WIDE)
    return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────────


def _eur(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
