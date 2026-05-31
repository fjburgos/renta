"""Integration tests against the synthetic DeGiro Account XLSX fixture.

Runs the full pipeline (parse → FX resolution → calculate) against a known
file and verifies IRPF box values per fiscal year.

Fixture: tests/dividends/fixtures/sample_account.xlsx (fictional EUR dividends, no
personal data, no network access required).
Regenerate with: python tests/dividends/fixtures/create_sample_account.py
"""

from decimal import Decimal
from pathlib import Path

import pytest

from renta.dividends import build_summary
from renta.dividends.ecb import ECBRatesProvider
from renta.dividends.models import DividendSummary

FIXTURE = Path(__file__).parent / "fixtures" / "sample_account.xlsx"


@pytest.fixture(scope="module")
def ecb() -> ECBRatesProvider:
    return ECBRatesProvider()


def _summary(ecb: ECBRatesProvider, year: int) -> DividendSummary:
    return build_summary(FIXTURE, year, ecb_provider=ecb)


class TestYear2021:
    def test_box_0029_total_gross(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2021).total_gross == Decimal("10.00")

    def test_box_0588_deduccion_dii(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2021).total_deductible_foreign_tax == Decimal("1.50")


class TestYear2022:
    def test_box_0029_total_gross(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2022).total_gross == Decimal("20.00")

    def test_box_0588_deduccion_dii(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2022).total_deductible_foreign_tax == Decimal("3.00")


class TestYear2023:
    def test_box_0029_total_gross(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2023).total_gross == Decimal("25.00")

    def test_box_0588_deduccion_dii(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2023).total_deductible_foreign_tax == Decimal("3.75")


class TestYear2024:
    def test_box_0029_total_gross(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2024).total_gross == Decimal("30.00")

    def test_box_0588_deduccion_dii(self, ecb: ECBRatesProvider) -> None:
        assert _summary(ecb, 2024).total_deductible_foreign_tax == Decimal("4.50")
