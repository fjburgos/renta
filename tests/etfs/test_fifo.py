"""Tests for the FIFO cost-basis engine (Art. 37.2 LIRPF)."""

import datetime
from decimal import Decimal

import pytest

from renta.etfs.fifo import FifoEngine
from renta.etfs.models import Transaction
from renta.utils.exceptions import NegativeStockError

ISIN = "IE0001000001"
PRODUCT = "World ETF"


def _buy(
    date: str,
    qty: int,
    total_eur: str,
    isin: str = ISIN,
    product: str = PRODUCT,
    order_id: str = "BUY-001",
) -> Transaction:
    return Transaction(
        date=datetime.date.fromisoformat(date),
        product=product,
        isin=isin,
        quantity=Decimal(str(qty)),
        total_eur=Decimal(total_eur),
        transaction_costs_eur=Decimal("0"),
        order_id=order_id,
    )


def _sell(
    date: str,
    qty: int,
    total_eur: str,
    isin: str = ISIN,
    product: str = PRODUCT,
    order_id: str = "SELL-001",
) -> Transaction:
    return Transaction(
        date=datetime.date.fromisoformat(date),
        product=product,
        isin=isin,
        quantity=Decimal(str(-qty)),
        total_eur=Decimal(total_eur),
        transaction_costs_eur=Decimal("0"),
        order_id=order_id,
    )


class TestSimpleBuySell:
    def test_gain(self) -> None:
        txs = [
            _buy("2024-01-10", 100, "-10000.00"),
            _sell("2024-06-20", 100, "12000.00"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 1
        event = events[0]
        assert event.acquisition_value == Decimal("10000.00")
        assert event.transfer_value == Decimal("12000.00")
        assert event.capital_gain == Decimal("2000.00")
        assert not event.is_loss

    def test_loss(self) -> None:
        txs = [
            _buy("2024-01-10", 100, "-10000.00"),
            _sell("2024-06-20", 100, "8000.00"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 1
        assert events[0].capital_gain == Decimal("-2000.00")
        assert events[0].is_loss


class TestPartialLotConsumption:
    def test_partial_sell_creates_one_event(self) -> None:
        txs = [
            _buy("2024-01-10", 100, "-10000.00"),
            _sell("2024-06-20", 40, "4400.00"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 1
        event = events[0]
        assert event.quantity == Decimal("40")
        assert event.acquisition_value == Decimal("4000.00")  # 40% of 10000
        assert event.transfer_value == Decimal("4400.00")
        assert event.capital_gain == Decimal("400.00")

    def test_remaining_lot_has_correct_quantity(self) -> None:
        txs = [
            _buy("2024-01-10", 100, "-10000.00"),
            _sell("2024-06-20", 40, "4400.00"),
        ]
        engine = FifoEngine()
        engine.process(txs)

        remaining = engine.remaining_lots()
        assert ISIN in remaining
        lots = remaining[ISIN]
        assert len(lots) == 1
        assert lots[0].quantity == Decimal("60")
        assert lots[0].unit_cost_eur == Decimal("100.00")  # unchanged per share

    def test_remaining_lot_cost_after_partial_sell(self) -> None:
        txs = [
            _buy("2024-01-10", 100, "-10002.00"),  # unit cost = 100.02
            _sell("2024-06-20", 80, "8800.00"),
        ]
        engine = FifoEngine()
        events = engine.process(txs)

        assert events[0].acquisition_value == Decimal("80") * Decimal("100.02")

        remaining = engine.remaining_lots()[ISIN]
        assert remaining[0].quantity == Decimal("20")
        assert remaining[0].unit_cost_eur == Decimal("100.02")


class TestMultipleLotsFifo:
    def test_sale_spans_two_lots(self) -> None:
        """Sell 150 shares: consumes all of Lot A (100) + 50 of Lot B (200)."""
        txs = [
            _buy("2024-01-10", 100, "-10000.00", order_id="BUY-A"),
            _buy("2024-03-15", 200, "-20000.00", order_id="BUY-B"),
            _sell("2024-06-20", 150, "16500.00"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 2

        lot_a_event = events[0]
        assert lot_a_event.acquisition_date == datetime.date(2024, 1, 10)
        assert lot_a_event.quantity == Decimal("100")
        assert lot_a_event.acquisition_value == Decimal("10000.00")

        lot_b_event = events[1]
        assert lot_b_event.acquisition_date == datetime.date(2024, 3, 15)
        assert lot_b_event.quantity == Decimal("50")
        assert lot_b_event.acquisition_value == Decimal("5000.00")  # 50/200 of 20000

    def test_fifo_order_respected(self) -> None:
        """Selling uses the oldest lot first."""
        txs = [
            _buy("2023-01-01", 10, "-500.00", order_id="OLD"),  # 50/share
            _buy("2024-01-01", 10, "-1000.00", order_id="NEW"),  # 100/share
            _sell("2024-06-01", 10, "700.00"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 1
        assert events[0].acquisition_date == datetime.date(2023, 1, 1)
        assert events[0].acquisition_value == Decimal("500.00")  # used old lot

    def test_multiple_sells_consume_lots_in_order(self) -> None:
        txs = [
            _buy("2024-01-01", 10, "-1000.00", order_id="BUY-1"),
            _buy("2024-02-01", 10, "-1100.00", order_id="BUY-2"),
            _sell("2024-06-01", 10, "1200.00", order_id="SELL-1"),
            _sell("2024-07-01", 10, "1250.00", order_id="SELL-2"),
        ]
        events = FifoEngine().process(txs)

        assert len(events) == 2
        assert events[0].acquisition_date == datetime.date(2024, 1, 1)
        assert events[1].acquisition_date == datetime.date(2024, 2, 1)


class TestEdgeCases:
    def test_no_lots_raises_negative_stock_error(self) -> None:
        txs = [_sell("2024-01-01", 10, "1000.00")]
        with pytest.raises(NegativeStockError):
            FifoEngine().process(txs)

    def test_oversell_raises_negative_stock_error(self) -> None:
        txs = [
            _buy("2024-01-01", 10, "-1000.00"),
            _sell("2024-06-01", 20, "2000.00"),  # more than available
        ]
        with pytest.raises(NegativeStockError):
            FifoEngine().process(txs)

    def test_no_remaining_lots_after_full_sale(self) -> None:
        txs = [
            _buy("2024-01-01", 10, "-1000.00"),
            _sell("2024-06-01", 10, "1100.00"),
        ]
        engine = FifoEngine()
        engine.process(txs)
        assert engine.remaining_lots() == {}

    def test_multiple_isins_tracked_independently(self) -> None:
        isin_a, isin_b = "IE0001000001", "IE0002000002"
        txs = [
            _buy("2024-01-01", 10, "-1000.00", isin=isin_a, order_id="A1"),
            _buy("2024-01-02", 5, "-500.00", isin=isin_b, order_id="B1"),
            _sell("2024-06-01", 10, "1200.00", isin=isin_a, order_id="A2"),
        ]
        engine = FifoEngine()
        events = engine.process(txs)

        assert len(events) == 1
        assert events[0].isin == isin_a
        remaining = engine.remaining_lots()
        assert isin_a not in remaining
        assert isin_b in remaining

    def test_acquisition_date_recorded_correctly(self) -> None:
        buy_date = datetime.date(2023, 3, 15)
        sell_date = datetime.date(2024, 9, 20)
        txs = [
            Transaction(
                date=buy_date,
                product=PRODUCT,
                isin=ISIN,
                quantity=Decimal("10"),
                total_eur=Decimal("-1000"),
                transaction_costs_eur=Decimal("0"),
                order_id="BUY",
            ),
            Transaction(
                date=sell_date,
                product=PRODUCT,
                isin=ISIN,
                quantity=Decimal("-10"),
                total_eur=Decimal("1100"),
                transaction_costs_eur=Decimal("0"),
                order_id="SELL",
            ),
        ]
        events = FifoEngine().process(txs)
        assert events[0].acquisition_date == buy_date
        assert events[0].transfer_date == sell_date
