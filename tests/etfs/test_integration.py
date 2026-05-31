"""Integration tests against the synthetic DeGiro XLSX fixture.

Runs the full pipeline (parse → FIFO → wash-sale) against a known file
and verifies monetary totals per fiscal year.

Fixture: tests/assets/sample_etf_transactions.xlsx (fictional data, no personal info).
Regenerate with: python tests/assets/create_sample_etf_regression.py
"""

from decimal import Decimal
from pathlib import Path

import pytest

from renta.etfs import _run_pipeline
from renta.etfs.models import CapitalGainEvent, WashSaleRecord
from renta.etfs.report import TaxSummary, build_tax_summary

FIXTURE = Path(__file__).parent.parent / "assets" / "sample_etf_transactions.xlsx"


@pytest.fixture(scope="module")
def pipeline() -> tuple[list[CapitalGainEvent], list[WashSaleRecord]]:
    return _run_pipeline(FIXTURE)


@pytest.fixture(scope="module")
def all_events(pipeline: tuple[list[CapitalGainEvent], list[WashSaleRecord]]) -> list[CapitalGainEvent]:
    return pipeline[0]


def _year_events(events: list[CapitalGainEvent], year: int) -> list[CapitalGainEvent]:
    return [e for e in events if e.transfer_date.year == year]


def _year_summary(
    pipeline: tuple[list[CapitalGainEvent], list[WashSaleRecord]], year: int
) -> TaxSummary:
    events, wash_records = pipeline
    return build_tax_summary(events, wash_records, year)


class TestYear2021:
    def test_total_sales(self, all_events: list[CapitalGainEvent]) -> None:
        events = _year_events(all_events, 2021)
        total = sum((e.transfer_value for e in events), Decimal("0"))
        assert round(total, 2) == Decimal("2998.00")

    def test_total_purchases(self, all_events: list[CapitalGainEvent]) -> None:
        events = _year_events(all_events, 2021)
        total = sum((e.acquisition_value for e in events), Decimal("0"))
        assert round(total, 2) == Decimal("2002.00")

    def test_net_result(self, pipeline: tuple[list[CapitalGainEvent], list[WashSaleRecord]]) -> None:
        summary = _year_summary(pipeline, 2021)
        assert summary.net_result == Decimal("996.00")


class TestYear2022:
    """Declarable operations for 2022: events whose transfer_date falls in 2022."""

    def test_total_sales(self, all_events: list[CapitalGainEvent]) -> None:
        events = _year_events(all_events, 2022)
        total = sum((e.transfer_value for e in events), Decimal("0"))
        assert round(total, 2) == Decimal("1798.00")

    def test_total_purchases(self, all_events: list[CapitalGainEvent]) -> None:
        events = _year_events(all_events, 2022)
        total = sum((e.acquisition_value for e in events), Decimal("0"))
        assert round(total, 2) == Decimal("2002.00")

    def test_net_result(self, pipeline: tuple[list[CapitalGainEvent], list[WashSaleRecord]]) -> None:
        summary = _year_summary(pipeline, 2022)
        assert summary.net_result == Decimal("-204.00")


class TestNoDeclarationAfter2022:
    def test_no_events_after_2022(self, all_events: list[CapitalGainEvent]) -> None:
        events_after = [e for e in all_events if e.transfer_date.year > 2022]
        assert events_after == []
