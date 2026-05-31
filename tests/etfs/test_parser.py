"""Tests for the DeGiro XLSX parser."""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from renta.etfs.parser import _merge_executions, _parse_raw_row, parse_degiro_xlsx
from renta.etfs.models import RawTransaction, Transaction
from renta.utils.exceptions import ParseError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_transactions.xlsx"


def _make_row(
    date: str = "14-05-2024",
    time: str = "09:00",
    product: str = "Test ETF",
    isin: str = "IE0001000001",
    exchange: str = "XET",
    venue: str = "XETA",
    quantity: float = 100.0,
    price: float = 100.0,
    price_currency: str = "EUR",
    local_value: float = -10000.0,
    local_currency: str = "EUR",
    eur_value: float = -10000.0,
    fx_rate: float | None = None,
    autofx: float = 0.0,
    costs: float | None = -2.0,
    total_eur: float = -10002.0,
    order_id: str = "ORD-001",
) -> tuple:  # type: ignore[type-arg]
    # Col 16 is blank in real DeGiro exports; order_id is at col 17
    return (
        date, time, product, isin, exchange, venue,
        quantity, price, price_currency,
        local_value, local_currency, eur_value,
        fx_rate, autofx, costs, total_eur, None, order_id, None,
    )


class TestParseRawRow:
    def test_buy_row(self) -> None:
        row = _make_row(quantity=100.0, total_eur=-10002.0)
        raw = _parse_raw_row(row)

        assert raw.date == datetime.date(2024, 5, 14)
        assert raw.isin == "IE0001000001"
        assert raw.quantity == Decimal("100")
        assert raw.total_eur == Decimal("-10002.0")
        assert raw.transaction_costs_eur == Decimal("-2.0")

    def test_sell_row(self) -> None:
        row = _make_row(quantity=-100.0, local_value=10800.0, eur_value=10800.0, total_eur=10798.0)
        raw = _parse_raw_row(row)

        assert raw.quantity == Decimal("-100")
        assert raw.total_eur == Decimal("10798.0")

    def test_none_costs_become_zero(self) -> None:
        row = _make_row(costs=None, total_eur=-10000.0)
        raw = _parse_raw_row(row)
        assert raw.transaction_costs_eur == Decimal("0")

    def test_date_parsing_dd_mm_yyyy(self) -> None:
        row = _make_row(date="31-12-2023")
        raw = _parse_raw_row(row)
        assert raw.date == datetime.date(2023, 12, 31)

    def test_invalid_date_raises_parse_error(self) -> None:
        row = _make_row(date="2024-05-14")  # wrong format
        with pytest.raises(ParseError, match="Cannot parse date"):
            _parse_raw_row(row)

    def test_empty_isin_raises_parse_error(self) -> None:
        row = _make_row(isin="")
        with pytest.raises(ParseError, match="ISIN"):
            _parse_raw_row(row)

    def test_zero_quantity_raises_parse_error(self) -> None:
        row = _make_row(quantity=0.0)
        with pytest.raises(ParseError, match="Quantity"):
            _parse_raw_row(row)

    def test_fx_rate_parsed_when_present(self) -> None:
        row = _make_row(fx_rate=1.08)
        raw = _parse_raw_row(row)
        assert raw.fx_rate == Decimal("1.08")

    def test_fx_rate_none_when_absent(self) -> None:
        row = _make_row(fx_rate=None)
        raw = _parse_raw_row(row)
        assert raw.fx_rate is None


class TestMergeExecutions:
    def _raw(
        self,
        order_id: str,
        date: str,
        isin: str,
        quantity: float,
        total_eur: float,
        costs: float = 0.0,
    ) -> RawTransaction:
        return RawTransaction(
            date=datetime.date.fromisoformat(date),
            time="09:00",
            product="Test Stock",
            isin=isin,
            exchange="MAD",
            execution_venue="GROW",
            quantity=Decimal(str(quantity)),
            price=Decimal("10"),
            price_currency="EUR",
            local_value=Decimal(str(total_eur)),
            local_currency="EUR",
            eur_value=Decimal(str(total_eur)),
            fx_rate=None,
            autofx_commission=Decimal("0"),
            transaction_costs_eur=Decimal(str(costs)),
            total_eur=Decimal(str(total_eur)),
            order_id=order_id,
        )

    def test_single_row_unchanged(self) -> None:
        raws = [self._raw("ORD-1", "2024-05-14", "ES0004000004", 100.0, -1000.0)]
        txs = _merge_executions(raws)
        assert len(txs) == 1
        assert txs[0].quantity == Decimal("100")
        assert txs[0].total_eur == Decimal("-1000.0")

    def test_split_same_order_same_day_merged(self) -> None:
        """The key case: two execution rows of the same order on the same day → one Transaction."""
        raws = [
            self._raw("ORD-999", "2024-05-14", "ES0004000004", 300.0, -3000.0, 0.0),
            self._raw("ORD-999", "2024-05-14", "ES0004000004", 200.0, -1983.0, -3.0),
        ]
        txs = _merge_executions(raws)

        assert len(txs) == 1
        tx = txs[0]
        assert tx.quantity == Decimal("500")
        assert tx.total_eur == Decimal("-4983.0")
        assert tx.transaction_costs_eur == Decimal("-3.0")
        assert tx.order_id == "ORD-999"
        assert tx.date == datetime.date(2024, 5, 14)

    def test_same_order_different_days_kept_separate(self) -> None:
        """Partial fills on different days are separate lots (different acquisition dates)."""
        raws = [
            self._raw("ORD-ABC", "2024-05-14", "ES0004000004", 150.0, -1500.0),
            self._raw("ORD-ABC", "2024-05-15", "ES0004000004", 50.0, -510.0),  # next day
        ]
        txs = _merge_executions(raws)

        assert len(txs) == 2
        dates = {tx.date for tx in txs}
        assert datetime.date(2024, 5, 14) in dates
        assert datetime.date(2024, 5, 15) in dates

    def test_different_orders_same_day_kept_separate(self) -> None:
        raws = [
            self._raw("ORD-1", "2024-05-14", "ES0004000004", 100.0, -1000.0),
            self._raw("ORD-2", "2024-05-14", "ES0004000004", 50.0, -500.0),
        ]
        txs = _merge_executions(raws)
        assert len(txs) == 2


class TestParseDegiroXlsx:
    def test_fixture_file_loads(self) -> None:
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture file not generated yet")
        txs = parse_degiro_xlsx(FIXTURE_PATH)
        assert len(txs) > 0

    def test_transactions_sorted_by_date(self) -> None:
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture file not generated yet")
        txs = parse_degiro_xlsx(FIXTURE_PATH)
        dates = [t.date for t in txs]
        assert dates == sorted(dates)

    def test_split_execution_merged_in_fixture(self) -> None:
        """ISIN 4 (ES0004000004) has 2 rows with same order_id on same day → 1 Transaction."""
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture file not generated yet")
        txs = parse_degiro_xlsx(FIXTURE_PATH)
        banco_alpha_buys = [
            t for t in txs if t.isin == "ES0004000004" and t.is_purchase
        ]
        assert len(banco_alpha_buys) == 1
        assert banco_alpha_buys[0].quantity == Decimal("500")
        assert banco_alpha_buys[0].total_eur == Decimal("-4983")
