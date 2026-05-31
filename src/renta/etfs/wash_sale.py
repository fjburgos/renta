"""
Wash-sale rule (regla antiaplicación) — Art. 33.5.d and 33.5.e Ley 35/2006 IRPF.

For securities listed on official markets (Art. 33.5.d):
  If you sell at a loss AND you purchase the same ISIN within 2 months before or after
  the sale date, the loss is not integrated in the current period. It is deferred and
  added to the cost basis of the replacement shares when those are eventually sold.

For unlisted securities (Art. 33.5.e): the window is 1 year.

This module applies the rule as a post-processing step over the list of CapitalGainEvent
produced by the FIFO engine.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from renta.etfs.models import CapitalGainEvent, Transaction, WashSaleRecord

# Conservative approximations: "2 months" = 61 days, "1 year" = 366 days.
# Rationale: using calendar days avoids dependency on dateutil and is the safe choice
# (errs on the side of deferring more losses, which is what the AEAT expects).
WINDOW_LISTED_DAYS = 61
WINDOW_UNLISTED_DAYS = 366


def apply_wash_sale_rule(
    events: list[CapitalGainEvent],
    transactions: list[Transaction],
    window_days: int = WINDOW_LISTED_DAYS,
) -> tuple[list[CapitalGainEvent], list[WashSaleRecord]]:
    """
    Detect and apply the wash-sale rule to a list of capital gain events.

    Args:
        events: Output from FifoEngine.process(), in chronological order.
        transactions: All transactions (purchases and sales) used to detect replacement buys.
        window_days: Wash-sale window in calendar days (61 for listed, 366 for unlisted).

    Returns:
        A tuple of:
        - The same events with wash_sale_deferred populated where applicable.
        - A list of WashSaleRecord for reporting and carry-forward tracking.
    """
    records: list[WashSaleRecord] = []
    purchases = [tx for tx in transactions if tx.is_purchase]

    for event in events:
        if not event.is_loss:
            continue

        replacement = _find_replacement_purchase(event, purchases, window_days)
        if replacement is None:
            continue

        deferred = abs(event.capital_gain)
        event.wash_sale_deferred = deferred

        deadline = event.transfer_date + datetime.timedelta(days=window_days)
        records.append(
            WashSaleRecord(
                loss_event=event,
                deferred_loss=deferred,
                reactivation_deadline=deadline,
                replacement_purchase_date=replacement.date,
            )
        )

    return events, records


def _find_replacement_purchase(
    loss_event: CapitalGainEvent,
    purchases: list[Transaction],
    window_days: int,
) -> Transaction | None:
    """
    Return the first purchase of the same ISIN that falls within the wash-sale window,
    excluding the purchase that IS the acquisition lot for this loss event (i.e., the
    purchase whose date matches acquisition_date).

    The window is symmetric: [sale_date - window_days, sale_date + window_days].
    The acquisition lot itself (same ISIN, same date as acquisition_date) is excluded
    because that is the lot being sold, not a replacement.
    """
    sale_date = loss_event.transfer_date
    window = datetime.timedelta(days=window_days)

    for purchase in purchases:
        if purchase.isin != loss_event.isin:
            continue
        if purchase.date == loss_event.acquisition_date:
            # This is the lot being sold, not a replacement
            continue
        if abs(sale_date - purchase.date) <= window:
            return purchase

    return None


def _days_between(a: datetime.date, b: datetime.date) -> int:
    return abs((a - b).days)
