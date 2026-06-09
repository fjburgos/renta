from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class YearlyBaseSummary:
    """Combined fiscal results for one year across all income sources."""

    year: int
    net_capital_gains: Decimal  # basket A: net G/P patrimoniales (can be negative)
    net_capital_income: Decimal  # basket B: dividends + account interest (usually positive)


@dataclass(frozen=True)
class CarryForwardEntry:
    """Pending loss from a prior year that has not yet been compensated.

    Amount is always positive; it represents a loss to be offset in future years.
    Art. 49.2 LIRPF: carry-forwards are valid for the four fiscal years following
    the year in which they were generated.
    """

    origin_year: int
    basket: str  # "A" (G/P patrimoniales) or "B" (rendimientos cap. mob.)
    amount: Decimal  # always > 0

    @property
    def expiry_year(self) -> int:
        """Last year in which this entry can be applied (origin + 4)."""
        return self.origin_year + 4


@dataclass(frozen=True)
class AppliedCarryForward:
    """Records how much of a CarryForwardEntry was consumed in a given year."""

    origin_year: int
    basket: str
    amount_applied: Decimal
    amount_remaining: Decimal


@dataclass
class YearlyCompensationResult:
    """Full compensation breakdown for a single fiscal year."""

    year: int

    # Raw figures before any compensation
    gross_basket_a: Decimal
    gross_basket_b: Decimal

    # Carry-forwards from prior years applied this year (FIFO, within-basket)
    applied_carry_forwards_a: list[AppliedCarryForward] = field(default_factory=list)
    applied_carry_forwards_b: list[AppliedCarryForward] = field(default_factory=list)

    # Cross-compensation (Art. 49.1.b LIRPF, max 25% of the receiving basket)
    cross_a_to_b: Decimal = Decimal("0")  # basket A loss offsetting basket B income
    cross_b_to_a: Decimal = Decimal("0")  # basket B loss offsetting basket A income

    # Final taxable amounts after all compensations
    net_basket_a: Decimal = Decimal("0")
    net_basket_b: Decimal = Decimal("0")

    # Carry-forwards generated this year (new pending losses)
    new_carry_forwards: list[CarryForwardEntry] = field(default_factory=list)

    # Carry-forwards that expired unused during this year
    expired_carry_forwards: list[CarryForwardEntry] = field(default_factory=list)


@dataclass
class CompensationResult:
    """Full multi-year compensation computation."""

    yearly_results: list[YearlyCompensationResult]

    # Carry-forwards still pending after the last processed year
    pending_carry_forwards: list[CarryForwardEntry] = field(default_factory=list)
