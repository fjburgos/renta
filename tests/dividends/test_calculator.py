"""Unit tests for calculator.py — isolated from XLSX parsing and ECB network."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from renta.dividends.calculator import _build_event, _convert, _find_fx_conversion
from renta.dividends.models import FxSource
from renta.dividends.parser import DividendGroup, FxConversion
from tests.dividends.conftest import FakeECB, NeverCalledECB

D = datetime.date
ZERO = Decimal("0")

APPLE_ISIN = "US0378331005"
ETF_ISIN = "IE0031442068"
DE_ISIN = "DE0005140008"


def _group(
    isin: str = APPLE_ISIN,
    date: str = "2024-05-17",
    currency: str = "USD",
    net: str = "1.25",
    withholding: str = "0.19",
    ticker: str = "APPLE INC",
) -> DividendGroup:
    return DividendGroup(
        date=D.fromisoformat(date),
        isin=isin,
        ticker=ticker,
        currency=currency,
        net_foreign=Decimal(net),
        withholding_foreign=Decimal(withholding),
    )


def _fx(
    fecha_valor: str = "2024-05-17",
    currency: str = "USD",
    fx_rate: str | None = "1.0897",
    net_foreign: str = "1.06",
    net_eur: str | None = "0.97",
) -> FxConversion:
    return FxConversion(
        fecha_valor=D.fromisoformat(fecha_valor),
        currency=currency,
        fx_rate=Decimal(fx_rate) if fx_rate is not None else None,
        net_foreign=Decimal(net_foreign),
        net_eur=Decimal(net_eur) if net_eur is not None else None,
    )


def _fx_index(*convs: FxConversion) -> dict[tuple[datetime.date, str], list[FxConversion]]:
    index: dict[tuple[datetime.date, str], list[FxConversion]] = {}
    for fx in convs:
        key = (fx.fecha_valor, fx.currency)
        index.setdefault(key, []).append(fx)
    return index


# ── _convert ──────────────────────────────────────────────────────────────────

class TestConvert:
    def test_gross_equals_sum_over_rate(self) -> None:
        group = _group(net="1.06", withholding="0.19")
        gross, wh, net = _convert(group, Decimal("1.0897"))
        assert gross.quantize(Decimal("0.01")) == (Decimal("1.25") / Decimal("1.0897")).quantize(Decimal("0.01"))

    def test_withholding_equals_wh_over_rate(self) -> None:
        group = _group(net="1.06", withholding="0.19")
        _, wh, _ = _convert(group, Decimal("1.0897"))
        assert wh.quantize(Decimal("0.01")) == (Decimal("0.19") / Decimal("1.0897")).quantize(Decimal("0.01"))

    def test_net_equals_net_over_rate(self) -> None:
        group = _group(net="1.06", withholding="0.19")
        _, _, net = _convert(group, Decimal("1.0897"))
        assert net.quantize(Decimal("0.01")) == (Decimal("1.06") / Decimal("1.0897")).quantize(Decimal("0.01"))

    def test_zero_withholding(self) -> None:
        group = _group(net="6.25", withholding="0.00", isin=ETF_ISIN)
        gross, wh, net = _convert(group, Decimal("1.0731"))
        assert wh == ZERO.quantize(Decimal("0.01"))
        assert gross == net


# ── _find_fx_conversion ───────────────────────────────────────────────────────

class TestFindFxConversion:
    def test_returns_none_when_no_candidates(self) -> None:
        group = _group()
        assert _find_fx_conversion(group, {}) is None

    def test_returns_single_candidate(self) -> None:
        conv = _fx()
        group = _group()
        result = _find_fx_conversion(group, _fx_index(conv))
        assert result is conv

    def test_matches_by_amount_when_multiple_candidates(self) -> None:
        conv_apple = _fx(net_foreign="1.06")
        conv_etf = _fx(net_foreign="6.25")  # same date/currency, different amount
        index = _fx_index(conv_apple, conv_etf)
        group = _group(net="1.25", withholding="0.19")  # net = 1.06
        result = _find_fx_conversion(group, index)
        assert result is conv_apple

    def test_no_match_on_wrong_date(self) -> None:
        conv = _fx(fecha_valor="2024-05-18")  # off by one day
        group = _group(date="2024-05-17")
        assert _find_fx_conversion(group, _fx_index(conv)) is None


# ── _build_event ──────────────────────────────────────────────────────────────

class TestBuildEvent:
    def test_eur_dividend_uses_degiro_source(self) -> None:
        group = _group(currency="EUR", isin=DE_ISIN, net="50.00", withholding="7.50")
        event = _build_event(group, {}, {}, NeverCalledECB())
        assert event.fx_source == FxSource.DEGIRO
        assert event.fx_rate is None

    def test_eur_gross_is_net_plus_withholding(self) -> None:
        group = _group(currency="EUR", isin=DE_ISIN, net="50.00", withholding="7.50")
        event = _build_event(group, {}, {}, NeverCalledECB())
        assert event.gross_amount == Decimal("57.50")
        assert event.net_amount == Decimal("50.00")

    def test_degiro_source_when_fx_conv_present(self) -> None:
        group = _group()
        conv = _fx()
        event = _build_event(group, _fx_index(conv), {}, NeverCalledECB())
        assert event.fx_source == FxSource.DEGIRO

    def test_degiro_net_eur_from_ingreso(self) -> None:
        group = _group()
        conv = _fx(net_eur="0.97")
        event = _build_event(group, _fx_index(conv), {}, NeverCalledECB())
        assert event.net_amount == Decimal("0.97")

    def test_ecb_fallback_when_no_fx_conv(self) -> None:
        group = _group()
        ecb = FakeECB().with_rate("USD", D(2024, 5, 17), Decimal("1.0897"))
        event = _build_event(group, {}, {}, ecb)
        assert event.fx_source == FxSource.ECB

    def test_ecb_fallback_when_tipo_is_none(self) -> None:
        group = _group()
        conv = _fx(fx_rate=None, net_eur="0.97")  # Tipo column was None
        ecb = FakeECB().with_rate("USD", D(2024, 5, 17), Decimal("1.0897"))
        event = _build_event(group, _fx_index(conv), {}, ecb)
        assert event.fx_source == FxSource.ECB

    def test_ecb_fallback_when_net_eur_missing(self) -> None:
        group = _group()
        conv = _fx(fx_rate="1.0897", net_eur=None)  # Ingreso row not found
        ecb = FakeECB().with_rate("USD", D(2024, 5, 17), Decimal("1.0897"))
        event = _build_event(group, _fx_index(conv), {}, ecb)
        assert event.fx_source == FxSource.ECB

    def test_override_beats_degiro(self) -> None:
        group = _group()
        conv = _fx()
        overrides = {(APPLE_ISIN, D(2024, 5, 17)): Decimal("1.09")}
        event = _build_event(group, _fx_index(conv), overrides, NeverCalledECB())
        assert event.fx_source == FxSource.OVERRIDE
        assert event.fx_rate == Decimal("1.09")

    def test_override_beats_ecb(self) -> None:
        group = _group()
        overrides = {(APPLE_ISIN, D(2024, 5, 17)): Decimal("1.09")}
        event = _build_event(group, {}, overrides, NeverCalledECB())
        assert event.fx_source == FxSource.OVERRIDE

    def test_irish_etf_note_true_for_ie_isin(self) -> None:
        group = _group(isin=ETF_ISIN, withholding="0.00")
        conv = _fx(net_foreign="6.25", net_eur="5.82")
        event = _build_event(group, _fx_index(conv), {}, NeverCalledECB())
        assert event.irish_etf_note is True

    def test_irish_etf_note_false_for_us_isin(self) -> None:
        group = _group(isin=APPLE_ISIN)
        conv = _fx()
        event = _build_event(group, _fx_index(conv), {}, NeverCalledECB())
        assert event.irish_etf_note is False


# ── deductible_tax cap ────────────────────────────────────────────────────────

class TestDeductibleTaxCap:
    def test_capped_at_19pct_when_withholding_exceeds_cap(self) -> None:
        # 26.375% withholding (Germany) on 100 EUR gross
        group = _group(currency="EUR", isin=DE_ISIN, net="73.625", withholding="26.375")
        event = _build_event(group, {}, {}, NeverCalledECB())
        cap = (Decimal("100.00") * Decimal("0.19")).quantize(Decimal("0.01"))
        assert event.deductible_foreign_tax == cap

    def test_full_deductible_at_15pct_withholding(self) -> None:
        # 15% US withholding is fully deductible (below 19% cap)
        group = _group(currency="EUR", isin=APPLE_ISIN, net="85.00", withholding="15.00")
        event = _build_event(group, {}, {}, NeverCalledECB())
        assert event.deductible_foreign_tax == Decimal("15.00")

    def test_zero_deductible_for_zero_withholding(self) -> None:
        group = _group(isin=ETF_ISIN, withholding="0.00")
        conv = _fx(net_foreign="6.25", net_eur="5.82")
        event = _build_event(group, _fx_index(conv), {}, NeverCalledECB())
        assert event.deductible_foreign_tax == ZERO
