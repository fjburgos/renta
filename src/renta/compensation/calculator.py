"""
Sequential year-by-year compensation of the base imponible del ahorro.

Rules implemented (Ley 35/2006 IRPF):
  Art. 49.1.a — G/P patrimoniales (basket A) compensate within basket A only.
  Art. 49.1.b — Negative basket A offsets basket B up to 25% of basket B, and vice versa.
  Art. 49.2   — Remaining negative balances carry forward to the next four fiscal years.
"""

from __future__ import annotations

from decimal import Decimal

from renta.compensation.models import (
    AppliedCarryForward,
    CarryForwardEntry,
    CompensationResult,
    YearlyBaseSummary,
    YearlyCompensationResult,
)

_ZERO = Decimal("0")
_CROSS_COMP_LIMIT = Decimal("0.25")
_CARRY_FORWARD_YEARS = 4


def calculate_compensation(summaries: list[YearlyBaseSummary]) -> CompensationResult:
    """
    Apply sequential year-by-year compensation starting from the oldest year.

    Args:
        summaries: Per-year basket results, in any order (will be sorted internally).

    Returns:
        CompensationResult with a YearlyCompensationResult per year and the
        list of carry-forwards still pending after the last year.
    """
    sorted_summaries = sorted(summaries, key=lambda s: s.year)
    carry_forwards: list[CarryForwardEntry] = []
    yearly_results: list[YearlyCompensationResult] = []

    for summary in sorted_summaries:
        result, carry_forwards = _process_year(summary, carry_forwards)
        yearly_results.append(result)

    return CompensationResult(
        yearly_results=yearly_results,
        pending_carry_forwards=carry_forwards,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _process_year(
    summary: YearlyBaseSummary,
    carry_forwards: list[CarryForwardEntry],
) -> tuple[YearlyCompensationResult, list[CarryForwardEntry]]:
    result = YearlyCompensationResult(
        year=summary.year,
        gross_basket_a=summary.net_capital_gains,
        gross_basket_b=summary.net_capital_income,
    )

    # Separate carry-forwards by basket; expire those past the 4-year limit.
    cf_a = [cf for cf in carry_forwards if cf.basket == "A"]
    cf_b = [cf for cf in carry_forwards if cf.basket == "B"]
    cf_a_active, cf_a_expired = _split_by_expiry(cf_a, summary.year)
    cf_b_active, cf_b_expired = _split_by_expiry(cf_b, summary.year)
    result.expired_carry_forwards = cf_a_expired + cf_b_expired

    basket_a = summary.net_capital_gains
    basket_b = summary.net_capital_income

    # Apply within-basket carry-forwards (only when the basket is positive).
    basket_a, applied_a, cf_a_remaining = _apply_carry_forwards(basket_a, cf_a_active)
    basket_b, applied_b, cf_b_remaining = _apply_carry_forwards(basket_b, cf_b_active)
    result.applied_carry_forwards_a = applied_a
    result.applied_carry_forwards_b = applied_b

    # Cross-compensation: negative A offsets up to 25% of positive B, and vice versa.
    basket_a, basket_b, cross_a_to_b = _cross_compensate(basket_a, basket_b)
    basket_b, basket_a, cross_b_to_a = _cross_compensate(basket_b, basket_a)
    result.cross_a_to_b = cross_a_to_b
    result.cross_b_to_a = cross_b_to_a

    result.net_basket_a = basket_a
    result.net_basket_b = basket_b

    # Generate new carry-forwards for any remaining negative balances.
    new_cf: list[CarryForwardEntry] = []
    if basket_a < _ZERO:
        new_cf.append(CarryForwardEntry(summary.year, "A", abs(basket_a)))
    if basket_b < _ZERO:
        new_cf.append(CarryForwardEntry(summary.year, "B", abs(basket_b)))
    result.new_carry_forwards = new_cf

    updated_carry_forwards = cf_a_remaining + cf_b_remaining + new_cf
    return result, updated_carry_forwards


def _split_by_expiry(
    entries: list[CarryForwardEntry], current_year: int
) -> tuple[list[CarryForwardEntry], list[CarryForwardEntry]]:
    """Split carry-forwards into (active, expired) for the given year."""
    active = [cf for cf in entries if cf.expiry_year >= current_year]
    expired = [cf for cf in entries if cf.expiry_year < current_year]
    return active, expired


def _apply_carry_forwards(
    balance: Decimal,
    carry_forwards: list[CarryForwardEntry],
) -> tuple[Decimal, list[AppliedCarryForward], list[CarryForwardEntry]]:
    """
    Apply carry-forwards (FIFO, oldest first) against a positive balance.

    Carry-forwards are never applied to a negative balance — they can only
    reduce a positive one.

    Returns:
        (updated_balance, applied_records, remaining_carry_forwards)
    """
    if balance <= _ZERO:
        return balance, [], carry_forwards

    applied: list[AppliedCarryForward] = []
    remaining: list[CarryForwardEntry] = []
    remaining_balance = balance

    for cf in carry_forwards:
        if remaining_balance <= _ZERO:
            remaining.append(cf)
            continue
        consumed = min(cf.amount, remaining_balance)
        remaining_balance -= consumed
        applied.append(
            AppliedCarryForward(
                origin_year=cf.origin_year,
                basket=cf.basket,
                amount_applied=consumed,
                amount_remaining=cf.amount - consumed,
            )
        )
        if cf.amount - consumed > _ZERO:
            remaining.append(CarryForwardEntry(cf.origin_year, cf.basket, cf.amount - consumed))

    return remaining_balance, applied, remaining


def _cross_compensate(
    source: Decimal, target: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Offset a negative source against a positive target (Art. 49.1.b LIRPF).

    The offset is limited to 25% of the target's positive balance.

    Returns:
        (updated_source, updated_target, amount_transferred)
    """
    if source >= _ZERO or target <= _ZERO:
        return source, target, _ZERO

    max_offset = target * _CROSS_COMP_LIMIT
    offset = min(abs(source), max_offset)
    return source + offset, target - offset, offset
