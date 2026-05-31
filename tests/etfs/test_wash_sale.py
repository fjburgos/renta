"""Tests for the wash-sale rule (Art. 33.5.d LIRPF — regla antiaplicación)."""

import datetime
from decimal import Decimal

import pytest

from renta.etfs.models import CapitalGainEvent, Transaction
from renta.etfs.wash_sale import WINDOW_LISTED_DAYS, apply_wash_sale_rule

ISIN = "IE0003000003"
PRODUCT = "Small Cap ETF"


def _loss_event(
    acquisition_date: str,
    transfer_date: str,
    loss: str,
    isin: str = ISIN,
) -> CapitalGainEvent:
    gain = Decimal(loss)  # should be negative
    return CapitalGainEvent(
        isin=isin,
        product=PRODUCT,
        acquisition_date=datetime.date.fromisoformat(acquisition_date),
        transfer_date=datetime.date.fromisoformat(transfer_date),
        quantity=Decimal("100"),
        acquisition_value=Decimal("10000"),
        transfer_value=Decimal("10000") + gain,
        capital_gain=gain,
    )


def _gain_event(
    acquisition_date: str,
    transfer_date: str,
    gain: str,
    isin: str = ISIN,
) -> CapitalGainEvent:
    g = Decimal(gain)
    return CapitalGainEvent(
        isin=isin,
        product=PRODUCT,
        acquisition_date=datetime.date.fromisoformat(acquisition_date),
        transfer_date=datetime.date.fromisoformat(transfer_date),
        quantity=Decimal("100"),
        acquisition_value=Decimal("10000"),
        transfer_value=Decimal("10000") + g,
        capital_gain=g,
    )


def _purchase(date: str, isin: str = ISIN) -> Transaction:
    return Transaction(
        date=datetime.date.fromisoformat(date),
        product=PRODUCT,
        isin=isin,
        quantity=Decimal("50"),
        total_eur=Decimal("-4302"),
        transaction_costs_eur=Decimal("2"),
        order_id=f"BUY-{date}",
    )


class TestNoWashSale:
    def test_loss_without_replacement_not_deferred(self) -> None:
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        purchases = [_purchase("2024-03-01")]  # this is the acquisition lot itself

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("0")
        assert len(records) == 0

    def test_loss_replacement_outside_window_not_deferred(self) -> None:
        """Replacement purchase at day 62 (> 61 day window) → not a wash sale."""
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        day_62 = (datetime.date(2024, 7, 10) + datetime.timedelta(days=62)).isoformat()
        purchases = [_purchase("2024-03-01"), _purchase(day_62)]

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("0")
        assert len(records) == 0

    def test_gain_never_triggers_wash_sale(self) -> None:
        event = _gain_event("2024-03-01", "2024-07-10", "+500")
        purchases = [_purchase("2024-03-01"), _purchase("2024-08-01")]

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("0")
        assert len(records) == 0

    def test_different_isin_not_a_wash_sale(self) -> None:
        event = _loss_event("2024-03-01", "2024-07-10", "-1504", isin="IE0003000003")
        purchases = [_purchase("2024-08-01", isin="IE0009999999")]  # different ISIN

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("0")


class TestWashSaleTriggered:
    def test_replacement_purchase_after_sale_within_window(self) -> None:
        """Classic scenario: sell at loss → rebuy within 41 days."""
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        day_41 = (datetime.date(2024, 7, 10) + datetime.timedelta(days=41)).isoformat()
        purchases = [_purchase("2024-03-01"), _purchase(day_41)]

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("1504")
        assert events[0].reported_gain == Decimal("0")
        assert len(records) == 1
        assert records[0].deferred_loss == Decimal("1504")

    def test_replacement_purchase_before_sale_within_window(self) -> None:
        """Anticipatory wash sale: rebuy within 61 days BEFORE the loss sale."""
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        day_minus_30 = (datetime.date(2024, 7, 10) - datetime.timedelta(days=30)).isoformat()
        purchases = [_purchase("2024-03-01"), _purchase(day_minus_30)]

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("1504")
        assert len(records) == 1

    def test_replacement_exactly_at_window_boundary(self) -> None:
        """Replacement at exactly day 61 IS within the window (<=)."""
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        day_61 = (datetime.date(2024, 7, 10) + datetime.timedelta(days=61)).isoformat()
        purchases = [_purchase("2024-03-01"), _purchase(day_61)]

        events, records = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == Decimal("1504")

    def test_wash_sale_record_has_correct_dates(self) -> None:
        event = _loss_event("2024-03-01", "2024-07-10", "-1504")
        replacement_date = "2024-08-20"
        purchases = [_purchase("2024-03-01"), _purchase(replacement_date)]

        _, records = apply_wash_sale_rule([event], purchases)

        assert records[0].replacement_purchase_date == datetime.date.fromisoformat(replacement_date)
        expected_deadline = datetime.date(2024, 7, 10) + datetime.timedelta(
            days=WINDOW_LISTED_DAYS
        )
        assert records[0].reactivation_deadline == expected_deadline

    def test_deferred_loss_equals_full_capital_loss(self) -> None:
        loss = Decimal("-756.50")
        event = _loss_event("2024-01-01", "2024-06-01", str(loss))
        purchases = [_purchase("2024-01-01"), _purchase("2024-07-01")]

        events, _ = apply_wash_sale_rule([event], purchases)

        assert events[0].wash_sale_deferred == abs(loss)
        assert events[0].reported_gain == Decimal("0")


class TestMixedEvents:
    def test_only_loss_events_evaluated(self) -> None:
        events = [
            _gain_event("2024-01-01", "2024-06-01", "+500"),
            _loss_event("2024-03-01", "2024-08-01", "-300"),
        ]
        purchases = [_purchase("2024-01-01"), _purchase("2024-03-01"), _purchase("2024-09-01")]

        result_events, records = apply_wash_sale_rule(events, purchases)

        assert result_events[0].wash_sale_deferred == Decimal("0")  # gain untouched
        assert result_events[1].wash_sale_deferred == Decimal("300")  # loss deferred
        assert len(records) == 1

    def test_multiple_losses_both_evaluated(self) -> None:
        loss_a = _loss_event("2024-01-01", "2024-05-01", "-200", isin="IE0001000001")
        loss_b = _loss_event("2024-02-01", "2024-07-01", "-400", isin="IE0002000002")

        buy_a = Transaction(
            date=datetime.date(2024, 6, 1),
            product="ETF A",
            isin="IE0001000001",
            quantity=Decimal("10"),
            total_eur=Decimal("-1000"),
            transaction_costs_eur=Decimal("0"),
            order_id="BUY-A2",
        )
        # No replacement purchase for B
        purchases = [buy_a]

        events, records = apply_wash_sale_rule([loss_a, loss_b], purchases)

        assert events[0].wash_sale_deferred == Decimal("200")  # A: wash sale
        assert events[1].wash_sale_deferred == Decimal("0")  # B: no wash sale
        assert len(records) == 1
