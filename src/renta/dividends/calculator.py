from __future__ import annotations

import datetime
from decimal import Decimal

from renta.dividends.ecb import FxRatesProvider
from renta.dividends.models import DividendEvent, DividendSummary, FxSource
from renta.dividends.parser import DividendGroup, FxConversion

_DEDUCTIBLE_RATE = Decimal("0.19")
_TWO = Decimal("0.01")


def build_summary(
    groups: list[DividendGroup],
    fx_conversions: list[FxConversion],
    tax_year: int,
    ecb: FxRatesProvider,
    fx_overrides: dict[tuple[str, datetime.date], Decimal],
) -> DividendSummary:
    # Index FX conversions by (fecha_valor, currency); keep list for amount-based disambiguation
    fx_index: dict[tuple[datetime.date, str], list[FxConversion]] = {}
    for fx in fx_conversions:
        key = (fx.fecha_valor, fx.currency)
        fx_index.setdefault(key, []).append(fx)

    events = [
        _build_event(g, fx_index, fx_overrides, ecb)
        for g in groups
        if g.date.year == tax_year
    ]

    zero = Decimal("0")
    total_gross = sum((e.gross_amount for e in events), zero)
    total_withholding = sum((e.foreign_withholding for e in events), zero)
    total_deductible = sum((e.deductible_foreign_tax for e in events), zero)
    by_country: dict[str, Decimal] = {}
    for e in events:
        country = e.isin[:2]
        by_country[country] = by_country.get(country, zero) + e.gross_amount

    return DividendSummary(
        tax_year=tax_year,
        events=events,
        total_gross=total_gross,
        total_foreign_withholding=total_withholding,
        total_deductible_foreign_tax=total_deductible,
        by_country=by_country,
    )


def _build_event(
    group: DividendGroup,
    fx_index: dict[tuple[datetime.date, str], list[FxConversion]],
    fx_overrides: dict[tuple[str, datetime.date], Decimal],
    ecb: FxRatesProvider,
) -> DividendEvent:
    override_key = (group.isin, group.date)

    if group.currency == "EUR":
        gross_eur = group.net_foreign + group.withholding_foreign
        withholding_eur = group.withholding_foreign
        net_eur = group.net_foreign
        fx_rate: Decimal | None = None
        fx_source = FxSource.DEGIRO
    elif override_key in fx_overrides:
        fx_rate = fx_overrides[override_key]
        gross_eur, withholding_eur, net_eur = _convert(group, fx_rate)
        fx_source = FxSource.OVERRIDE
    else:
        fx_conv = _find_fx_conversion(group, fx_index)
        if fx_conv is not None and fx_conv.fx_rate is not None and fx_conv.net_eur is not None:
            fx_rate = fx_conv.fx_rate
            withholding_eur = group.withholding_foreign / fx_rate
            net_eur = fx_conv.net_eur
            gross_eur = net_eur + withholding_eur
            fx_source = FxSource.DEGIRO
        else:
            # Fallback: ECB rate (auto, no user interaction)
            fx_rate = ecb.get_rate(group.currency, group.date)
            gross_eur, withholding_eur, net_eur = _convert(group, fx_rate)
            fx_source = FxSource.ECB

    deductible = min(withholding_eur, gross_eur * _DEDUCTIBLE_RATE)

    return DividendEvent(
        date=group.date,
        isin=group.isin,
        ticker=group.ticker,
        gross_amount=_round(gross_eur),
        foreign_withholding=_round(withholding_eur),
        deductible_foreign_tax=_round(deductible),
        net_amount=_round(net_eur),
        original_currency=group.currency,
        fx_rate=fx_rate,
        fx_source=fx_source,
        irish_etf_note=group.isin.startswith("IE"),
    )


def _find_fx_conversion(
    group: DividendGroup,
    fx_index: dict[tuple[datetime.date, str], list[FxConversion]],
) -> FxConversion | None:
    candidates = fx_index.get((group.date, group.currency), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Multiple candidates (rare: two dividends same currency same date) — match by amount
    net_expected = group.net_foreign
    for c in candidates:
        if abs(c.net_foreign - net_expected) < Decimal("0.02"):
            return c
    return candidates[0]


def _convert(group: DividendGroup, fx_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    gross_foreign = group.net_foreign + group.withholding_foreign
    gross_eur = gross_foreign / fx_rate
    withholding_eur = group.withholding_foreign / fx_rate
    net_eur = group.net_foreign / fx_rate
    return gross_eur, withholding_eur, net_eur


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO)
