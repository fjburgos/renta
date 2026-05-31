"""End-to-end tests for the dividends pipeline (parse → calculate → report)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from renta.dividends import build_summary, calculate
from renta.dividends.models import FxSource
from tests.dividends.conftest import (
    FakeECB,
    NeverCalledECB,
    build_xlsx,
    dividendo,
    ingreso,
    retencion,
    retirada,
)

DATE_2024 = "17-05-2024"
DATE_VALOR_2024 = "16-05-2024"
FX_DATE_2024 = "18-05-2024"

DATE_ETF = "27-06-2024"
DATE_VALOR_ETF = "26-06-2024"
FX_DATE_ETF = "28-06-2024"

APPLE_ISIN = "US0378331005"
ETF_ISIN = "IE0031442068"
DE_ISIN = "DE0005140008"


# ── helpers ───────────────────────────────────────────────────────────────────

def _apple_with_fx(tmp_path: Path) -> Path:
    """Apple USD dividend + withholding + DeGiro Retirada/Ingreso rows."""
    return build_xlsx(tmp_path, [
        dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
        retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
        retirada(FX_DATE_2024, DATE_VALOR_2024, "USD", -1.06, 1.0897),
        ingreso(FX_DATE_2024, DATE_VALOR_2024, 0.97),
    ])


def _irish_etf(tmp_path: Path) -> Path:
    """Irish ETF USD dividend, no withholding + DeGiro FX rows."""
    return build_xlsx(tmp_path, [
        dividendo(DATE_ETF, ETF_ISIN, "ISHARES S&P 500", "USD", 6.25, DATE_VALOR_ETF),
        retirada(FX_DATE_ETF, DATE_VALOR_ETF, "USD", -6.25, 1.0731),
        ingreso(FX_DATE_ETF, DATE_VALOR_ETF, 5.82),
    ])


# ── 1. USD dividend with DeGiro FX rows ───────────────────────────────────────

class TestAppleWithFxRows:
    def test_fx_source_is_degiro(self, tmp_path: Path) -> None:
        summary = build_summary(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].fx_source == FxSource.DEGIRO

    def test_net_eur_from_ingreso(self, tmp_path: Path) -> None:
        summary = build_summary(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        assert event.net_amount == Decimal("0.97")

    def test_gross_eur_is_net_plus_withholding(self, tmp_path: Path) -> None:
        summary = build_summary(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        # withholding_eur = 0.19 / 1.0897; gross_eur = 0.97 + withholding_eur
        expected_withholding = (Decimal("0.19") / Decimal("1.0897")).quantize(Decimal("0.01"))
        expected_gross = (Decimal("0.97") + expected_withholding).quantize(Decimal("0.01"))
        assert event.foreign_withholding == expected_withholding
        assert event.gross_amount == expected_gross

    def test_deductible_tax_below_19pct(self, tmp_path: Path) -> None:
        summary = build_summary(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        # withholding ≈ 15% of gross → fully deductible (below 19% cap)
        assert event.deductible_foreign_tax == event.foreign_withholding

    def test_not_irish_etf(self, tmp_path: Path) -> None:
        summary = build_summary(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert not summary.events[0].irish_etf_note

    def test_report_has_no_fallback_section(self, tmp_path: Path) -> None:
        report = calculate(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert "MODO FALLBACK" not in report

    def test_report_contains_box_0029(self, tmp_path: Path) -> None:
        report = calculate(_apple_with_fx(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert "0029" in report


# ── 2. Irish ETF — no withholding ─────────────────────────────────────────────

class TestIrishEtfNoWithholding:
    def test_foreign_withholding_is_zero(self, tmp_path: Path) -> None:
        summary = build_summary(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].foreign_withholding == Decimal("0")

    def test_deductible_tax_is_zero(self, tmp_path: Path) -> None:
        summary = build_summary(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].deductible_foreign_tax == Decimal("0")

    def test_irish_etf_note_is_true(self, tmp_path: Path) -> None:
        summary = build_summary(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].irish_etf_note

    def test_gross_eur_equals_ingreso_amount(self, tmp_path: Path) -> None:
        summary = build_summary(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].gross_amount == Decimal("5.82")

    def test_report_contains_irish_etf_note(self, tmp_path: Path) -> None:
        report = calculate(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert "IE..." in report or "Irlanda" in report

    def test_report_marks_event_with_flag(self, tmp_path: Path) -> None:
        report = calculate(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert "⚠IE" in report

    def test_no_dii_section_for_irish_etf(self, tmp_path: Path) -> None:
        report = calculate(_irish_etf(tmp_path), 2024, ecb_provider=NeverCalledECB())
        assert "doble imposición" not in report.lower() or "0,00" in report


# ── 3. EUR dividend — no FX conversion ───────────────────────────────────────

class TestEurDividend:
    def test_fx_rate_is_none(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
            retencion("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", -7.5),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].fx_rate is None

    def test_gross_reconstructed_from_net_plus_withholding(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
            retencion("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", -7.5),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert summary.events[0].gross_amount == Decimal("57.50")
        assert summary.events[0].net_amount == Decimal("50.00")
        assert summary.events[0].foreign_withholding == Decimal("7.50")

    def test_ecb_not_called_for_eur(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
        ])
        # NeverCalledECB raises if called — verifies ECB is not invoked for EUR dividends
        build_summary(path, 2024, ecb_provider=NeverCalledECB())


# ── 4. ECB fallback — missing Retirada/Ingreso ────────────────────────────────

class TestEcbFallback:
    def _path(self, tmp_path: Path) -> Path:
        return build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
            retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
            # No Retirada / Ingreso rows
        ])

    def _ecb(self) -> FakeECB:
        return FakeECB().with_rate(
            "USD",
            datetime.date(2024, 5, 16),
            Decimal("1.0897"),
        )

    def test_fx_source_is_ecb(self, tmp_path: Path) -> None:
        summary = build_summary(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        assert summary.events[0].fx_source == FxSource.ECB

    def test_gross_eur_computed_from_ecb_rate(self, tmp_path: Path) -> None:
        summary = build_summary(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        event = summary.events[0]
        # gross_foreign = net(1.25) + withholding(0.19) = 1.44
        expected_gross = (Decimal("1.44") / Decimal("1.0897")).quantize(Decimal("0.01"))
        assert event.gross_amount == expected_gross

    def test_report_contains_fallback_section(self, tmp_path: Path) -> None:
        report = calculate(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        assert "MODO FALLBACK" in report

    def test_report_fallback_explains_expected_pattern(self, tmp_path: Path) -> None:
        report = calculate(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        assert "Retirada Cambio de Divisa" in report
        assert "Ingreso Cambio de Divisa" in report

    def test_report_fallback_shows_ecb_source(self, tmp_path: Path) -> None:
        report = calculate(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        assert "[ECB]" in report

    def test_report_fallback_shows_fx_rate(self, tmp_path: Path) -> None:
        report = calculate(self._path(tmp_path), 2024, ecb_provider=self._ecb())
        assert "1.0897" in report


# ── 5. ECB fallback — Retirada present but Tipo=None ─────────────────────────

class TestEcbFallbackTipoNone:
    def test_falls_back_to_ecb_when_tipo_is_none(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("13-08-2021", APPLE_ISIN, "APPLE INC", "USD", 1.1, "12-08-2021"),
            retencion("13-08-2021", APPLE_ISIN, "APPLE INC", "USD", -0.17, "12-08-2021"),
            # Retirada with Tipo=None (pre-2022 format where rate was not stored)
            retirada("14-08-2021", "12-08-2021", "USD", -0.93, tipo=None),  # type: ignore[arg-type]
            ingreso("14-08-2021", "12-08-2021", 0.81),
        ])
        ecb = FakeECB().with_rate("USD", datetime.date(2021, 8, 12), Decimal("1.1807"))
        summary = build_summary(path, 2021, ecb_provider=ecb)
        assert summary.events[0].fx_source == FxSource.ECB

    def test_retirada_tipo_none_uses_ecb_rate(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("13-08-2021", APPLE_ISIN, "APPLE INC", "USD", 1.1, "12-08-2021"),
            retencion("13-08-2021", APPLE_ISIN, "APPLE INC", "USD", -0.17, "12-08-2021"),
            retirada("14-08-2021", "12-08-2021", "USD", -0.93, tipo=None),  # type: ignore[arg-type]
            ingreso("14-08-2021", "12-08-2021", 0.81),
        ])
        ecb = FakeECB().with_rate("USD", datetime.date(2021, 8, 12), Decimal("1.1807"))
        summary = build_summary(path, 2021, ecb_provider=ecb)
        # gross_foreign = net(1.10) + withholding(0.17) = 1.27
        expected_gross = (Decimal("1.27") / Decimal("1.1807")).quantize(Decimal("0.01"))
        assert summary.events[0].gross_amount == expected_gross


# ── 6. Override takes precedence ──────────────────────────────────────────────

class TestFxOverride:
    def test_override_source(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
            retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
        ])
        overrides = {(APPLE_ISIN, datetime.date(2024, 5, 16)): Decimal("1.09")}
        summary = build_summary(path, 2024, fx_overrides=overrides, ecb_provider=NeverCalledECB())
        assert summary.events[0].fx_source == FxSource.OVERRIDE

    def test_override_beats_degiro_rows(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
            retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
            retirada(FX_DATE_2024, DATE_VALOR_2024, "USD", -1.06, 1.0897),
            ingreso(FX_DATE_2024, DATE_VALOR_2024, 0.97),
        ])
        overrides = {(APPLE_ISIN, datetime.date(2024, 5, 16)): Decimal("1.09")}
        summary = build_summary(path, 2024, fx_overrides=overrides, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        assert event.fx_source == FxSource.OVERRIDE
        # gross_foreign = net(1.25) + withholding(0.19) = 1.44
        expected_gross = (Decimal("1.44") / Decimal("1.09")).quantize(Decimal("0.01"))
        assert event.gross_amount == expected_gross

    def test_override_shown_in_fallback_report(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
        ])
        overrides = {(APPLE_ISIN, datetime.date(2024, 5, 16)): Decimal("1.09")}
        report = calculate(path, 2024, fx_overrides=overrides, ecb_provider=NeverCalledECB())
        assert "[OVERRIDE]" in report


# ── 7. Year filter ────────────────────────────────────────────────────────────

class TestYearFilter:
    def test_only_requested_year_included(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2023", DE_ISIN, "DEUTSCHE BANK", "EUR", 30.0),
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert len(summary.events) == 1
        assert summary.events[0].date.year == 2024

    def test_totals_only_from_requested_year(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2023", DE_ISIN, "DEUTSCHE BANK", "EUR", 30.0),
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert summary.total_gross == Decimal("50.00")


# ── 8. Deductible tax capped at 19 % ─────────────────────────────────────────

class TestDeductibleTaxCap:
    def test_cap_at_19pct_when_withholding_exceeds_cap(self, tmp_path: Path) -> None:
        # German stock: ~26% withholding → capped at 19% of gross
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 73.625),
            retencion("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", -26.375),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        cap = (event.gross_amount * Decimal("0.19")).quantize(Decimal("0.01"))
        assert event.deductible_foreign_tax == cap
        assert event.deductible_foreign_tax < event.foreign_withholding

    def test_no_cap_when_withholding_below_19pct(self, tmp_path: Path) -> None:
        # USA: 15% withholding via W-8BEN → fully deductible
        path = build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
            retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
            retirada(FX_DATE_2024, DATE_VALOR_2024, "USD", -1.06, 1.0897),
            ingreso(FX_DATE_2024, DATE_VALOR_2024, 0.97),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        event = summary.events[0]
        assert event.deductible_foreign_tax == event.foreign_withholding


# ── 9. Multiple events — totals ───────────────────────────────────────────────

class TestMultipleEvents:
    def test_total_gross_is_sum_of_events(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
            retencion("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", -7.5),
            dividendo("20-04-2024", "GB00B4MYWJ89", "VANGUARD ETF", "EUR", 30.0),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert summary.total_gross == Decimal("57.50") + Decimal("30.00")

    def test_by_country_groups_correctly(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo("15-03-2024", DE_ISIN, "DEUTSCHE BANK", "EUR", 50.0),
            dividendo("20-04-2024", "DE0005140009", "SIEMENS", "EUR", 25.0),
        ])
        summary = build_summary(path, 2024, ecb_provider=NeverCalledECB())
        assert "DE" in summary.by_country
        assert summary.by_country["DE"] == Decimal("75.00")

    def test_dii_section_present_when_withholding_exists(self, tmp_path: Path) -> None:
        path = build_xlsx(tmp_path, [
            dividendo(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", 1.25, DATE_VALOR_2024),
            retencion(DATE_2024, APPLE_ISIN, "APPLE INC", "USD", -0.19, DATE_VALOR_2024),
            retirada(FX_DATE_2024, DATE_VALOR_2024, "USD", -1.06, 1.0897),
            ingreso(FX_DATE_2024, DATE_VALOR_2024, 0.97),
        ])
        report = calculate(path, 2024, ecb_provider=NeverCalledECB())
        assert "doble imposición" in report.lower()
        assert "0588" in report


# ── 10. Year boundary: dividend Dec-31, Retirada Jan-1 not in file ─────────────

class TestYearBoundary:
    def test_ecb_fallback_when_retirada_in_following_year(self, tmp_path: Path) -> None:
        # Dividend on Dec 31, Retirada would be Jan 1 but the XLSX only covers the year
        path = build_xlsx(tmp_path, [
            dividendo("31-12-2024", APPLE_ISIN, "APPLE INC", "USD", 1.25, "30-12-2024"),
            retencion("31-12-2024", APPLE_ISIN, "APPLE INC", "USD", -0.19, "30-12-2024"),
            # Retirada with FechaValor=30-12-2024 would be Fecha=01-01-2025 — not in file
        ])
        ecb = FakeECB().with_rate("USD", datetime.date(2024, 12, 30), Decimal("1.04"))
        summary = build_summary(path, 2024, ecb_provider=ecb)
        assert summary.events[0].fx_source == FxSource.ECB

    def test_fecha_in_new_year_fecha_valor_in_old_year_assigned_to_old_year(self, tmp_path: Path) -> None:
        # Real case: Fecha=03-01-2022, Fecha valor=31-12-2021 → fiscal year 2021
        path = build_xlsx(tmp_path, [
            dividendo("03-01-2022", ETF_ISIN, "ISHARES CORE S&P 500", "USD", 5.34, "31-12-2021"),
        ])
        ecb = FakeECB().with_rate("USD", datetime.date(2021, 12, 31), Decimal("1.13"))
        summary = build_summary(path, 2021, ecb_provider=ecb)
        assert len(summary.events) == 1
        assert summary.events[0].date == datetime.date(2021, 12, 31)

    def test_fecha_in_new_year_excluded_from_new_year(self, tmp_path: Path) -> None:
        # Same dividend must not appear in 2022 summary
        path = build_xlsx(tmp_path, [
            dividendo("03-01-2022", ETF_ISIN, "ISHARES CORE S&P 500", "USD", 5.34, "31-12-2021"),
        ])
        summary = build_summary(path, 2022, ecb_provider=NeverCalledECB())
        assert len(summary.events) == 0
