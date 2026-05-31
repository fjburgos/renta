"""Domain models for ETF and stock capital gains calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RawTransaction:
    """A single row as read from the DeGiro XLSX export. May be part of a split execution."""

    date: date
    time: str
    product: str
    isin: str
    exchange: str
    execution_venue: str
    quantity: Decimal  # positive = purchase, negative = sale
    price: Decimal
    price_currency: str
    local_value: Decimal
    local_currency: str
    eur_value: Decimal
    fx_rate: Decimal | None
    autofx_commission: Decimal
    transaction_costs_eur: Decimal  # 0 when None in XLSX
    total_eur: Decimal  # negative = purchase (outflow), positive = sale (inflow)
    order_id: str


@dataclass(frozen=True)
class Transaction:
    """
    A consolidated transaction after merging split executions (same order_id + same date).
    This is the unit of work consumed by the FIFO engine.
    """

    date: date
    product: str
    isin: str
    quantity: Decimal  # positive = purchase, negative = sale
    total_eur: Decimal  # negative = purchase, positive = sale; includes all costs
    transaction_costs_eur: Decimal
    order_id: str

    @property
    def is_purchase(self) -> bool:
        return self.quantity > Decimal("0")

    @property
    def is_sale(self) -> bool:
        return self.quantity < Decimal("0")

    @property
    def abs_quantity(self) -> Decimal:
        return abs(self.quantity)

    @property
    def abs_total_eur(self) -> Decimal:
        """
        Absolute EUR amount.
        For purchases: acquisition value (price + costs).
        For sales: transfer value (proceeds net of costs).
        Both already embedded in total_eur by DeGiro.
        """
        return abs(self.total_eur)


@dataclass(frozen=True)
class Lot:
    """A purchase lot tracked in FIFO order. unit_cost_eur is constant throughout the lot's life."""

    date: date
    isin: str
    quantity: Decimal
    unit_cost_eur: Decimal  # cost per share including proportional acquisition costs

    @property
    def total_acquisition_value(self) -> Decimal:
        return self.quantity * self.unit_cost_eur


@dataclass
class CapitalGainEvent:
    """
    Fiscal result of a FIFO-matched portion of a sale against one acquisition lot.
    A single sale transaction may generate multiple events when it consumes several lots.
    """

    isin: str
    product: str
    acquisition_date: date
    transfer_date: date
    quantity: Decimal
    acquisition_value: Decimal  # Art. 35.1 LIRPF: cost basis for this portion
    transfer_value: Decimal  # Art. 35.2 LIRPF: net proceeds for this portion
    capital_gain: Decimal  # transfer_value - acquisition_value (positive = gain, negative = loss)
    wash_sale_deferred: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def is_loss(self) -> bool:
        return self.capital_gain < Decimal("0")

    @property
    def reported_gain(self) -> Decimal:
        """Effective gain/loss after wash-sale deferral. This is what goes into the tax return."""
        return self.capital_gain + self.wash_sale_deferred


@dataclass
class WashSaleRecord:
    """
    Records a loss that has been deferred under Art. 33.5.d LIRPF (regla antiaplicación).
    The deferred loss must be declared when the replacement shares are eventually sold.
    """

    loss_event: CapitalGainEvent
    deferred_loss: Decimal  # positive amount (the loss magnitude)
    reactivation_deadline: date  # date by which a replacement purchase triggers the rule
    replacement_purchase_date: date | None = None  # the purchase that triggered the wash sale
