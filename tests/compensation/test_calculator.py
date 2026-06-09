"""Tests for the base imponible del ahorro compensation calculator."""

from decimal import Decimal

import pytest

from renta.compensation.calculator import calculate_compensation
from renta.compensation.models import YearlyBaseSummary


def D(s: str) -> Decimal:
    return Decimal(s)


# ── Basic single-year cases ───────────────────────────────────────────────────


def test_positive_both_baskets_no_compensation_needed():
    summaries = [YearlyBaseSummary(2024, D("200"), D("50"))]
    result = calculate_compensation(summaries)
    yr = result.yearly_results[0]
    assert yr.net_basket_a == D("200")
    assert yr.net_basket_b == D("50")
    assert yr.new_carry_forwards == []
    assert result.pending_carry_forwards == []


def test_loss_in_basket_a_generates_carry_forward():
    summaries = [YearlyBaseSummary(2022, D("-148.30"), D("27.35"))]
    result = calculate_compensation(summaries)
    yr = result.yearly_results[0]

    # Cross-compensation: A can offset up to 25% of B = 6.8375
    expected_cross = D("27.35") * D("0.25")
    assert yr.cross_a_to_b == expected_cross
    assert yr.net_basket_b == D("27.35") - expected_cross
    # Basket A stays negative after cross-comp; the remainder is the carry-forward
    assert yr.net_basket_a == -(D("148.30") - expected_cross)
    expected_cf_amount = D("148.30") - expected_cross
    assert len(result.pending_carry_forwards) == 1
    cf = result.pending_carry_forwards[0]
    assert cf.basket == "A"
    assert cf.origin_year == 2022
    assert cf.expiry_year == 2026
    assert cf.amount == expected_cf_amount


def test_carry_forward_applied_against_future_gain():
    summaries = [
        YearlyBaseSummary(2022, D("-100"), D("0")),
        YearlyBaseSummary(2023, D("60"), D("0")),
    ]
    result = calculate_compensation(summaries)

    yr2022 = result.yearly_results[0]
    assert yr2022.net_basket_a == D("-100")  # stays negative; no basket B to cross-compensate
    assert len(yr2022.new_carry_forwards) == 1
    assert yr2022.new_carry_forwards[0].amount == D("100")

    yr2023 = result.yearly_results[1]
    assert len(yr2023.applied_carry_forwards_a) == 1
    applied = yr2023.applied_carry_forwards_a[0]
    assert applied.amount_applied == D("60")
    assert applied.amount_remaining == D("40")
    assert yr2023.net_basket_a == D("0")

    # 40 still pending
    assert len(result.pending_carry_forwards) == 1
    assert result.pending_carry_forwards[0].amount == D("40")


def test_carry_forward_fully_consumed_by_large_gain():
    summaries = [
        YearlyBaseSummary(2022, D("-100"), D("0")),
        YearlyBaseSummary(2023, D("200"), D("0")),
    ]
    result = calculate_compensation(summaries)
    yr2023 = result.yearly_results[1]
    assert yr2023.net_basket_a == D("100")
    assert result.pending_carry_forwards == []


def test_cross_compensation_limit_25_percent():
    # Basket A loss = 50, basket B = 100 → max cross = 25
    summaries = [YearlyBaseSummary(2022, D("-50"), D("100"))]
    result = calculate_compensation(summaries)
    yr = result.yearly_results[0]
    assert yr.cross_a_to_b == D("25")
    assert yr.net_basket_b == D("75")
    # Remaining loss in A after cross-comp: -50 + 25 = -25 (goes to carry-forward)
    assert yr.net_basket_a == D("-25")
    assert result.pending_carry_forwards[0].amount == D("25")


def test_cross_compensation_capped_by_actual_loss():
    # Basket A loss = 5, basket B = 100 → 25% of B = 25, but loss is only 5
    summaries = [YearlyBaseSummary(2022, D("-5"), D("100"))]
    result = calculate_compensation(summaries)
    yr = result.yearly_results[0]
    assert yr.cross_a_to_b == D("5")
    assert yr.net_basket_b == D("95")
    assert yr.net_basket_a == D("0")
    assert result.pending_carry_forwards == []


def test_cross_compensation_b_to_a():
    # Basket B loss, basket A positive
    summaries = [YearlyBaseSummary(2022, D("100"), D("-20"))]
    result = calculate_compensation(summaries)
    yr = result.yearly_results[0]
    # 25% of A = 25; B loss is 20, so 20 is applied
    assert yr.cross_b_to_a == D("20")
    assert yr.net_basket_a == D("80")
    assert yr.net_basket_b == D("0")
    assert result.pending_carry_forwards == []


def test_carry_forward_expires_after_4_years():
    summaries = [
        YearlyBaseSummary(2020, D("-100"), D("0")),
        # 2021, 2022, 2023, 2024: no sales, no income
        YearlyBaseSummary(2025, D("50"), D("0")),  # loss from 2020 expired
    ]
    result = calculate_compensation(summaries)
    yr2025 = result.yearly_results[1]

    # The 2020 loss expires in 2025 (expiry_year = 2024, so 2025 > 2024)
    assert len(yr2025.expired_carry_forwards) == 1
    assert yr2025.expired_carry_forwards[0].origin_year == 2020
    # No carry-forward applied; basket A = full gain
    assert yr2025.net_basket_a == D("50")
    assert yr2025.applied_carry_forwards_a == []


def test_carry_forward_still_valid_in_expiry_year():
    # Loss from 2021 expires in 2025 (the 4th following year)
    summaries = [
        YearlyBaseSummary(2021, D("-100"), D("0")),
        YearlyBaseSummary(2025, D("80"), D("0")),
    ]
    result = calculate_compensation(summaries)
    yr2025 = result.yearly_results[1]
    # expiry_year = 2025, current_year = 2025 → still active
    assert yr2025.expired_carry_forwards == []
    assert len(yr2025.applied_carry_forwards_a) == 1
    assert yr2025.applied_carry_forwards_a[0].amount_applied == D("80")
    assert result.pending_carry_forwards[0].amount == D("20")


def test_no_carry_forward_applied_to_negative_basket():
    # Current year basket A is already negative; carry-forward stays intact
    summaries = [
        YearlyBaseSummary(2022, D("-100"), D("0")),
        YearlyBaseSummary(2023, D("-50"), D("0")),
    ]
    result = calculate_compensation(summaries)
    yr2023 = result.yearly_results[1]
    assert yr2023.applied_carry_forwards_a == []
    # Both losses accumulate
    pending_amounts = sorted(cf.amount for cf in result.pending_carry_forwards)
    assert pending_amounts == [D("50"), D("100")]


def test_realistic_2022_data():
    """Reproduce the actual 2022 situation from the user's data."""
    summaries = [
        YearlyBaseSummary(2021, D("169.59"), D("5.37")),
        YearlyBaseSummary(2022, D("-148.30"), D("27.35")),
    ]
    result = calculate_compensation(summaries)

    yr2021 = result.yearly_results[0]
    assert yr2021.net_basket_a == D("169.59")
    assert yr2021.new_carry_forwards == []

    yr2022 = result.yearly_results[1]
    # 25% of 27.35 = 6.8375 applied cross A→B
    assert yr2022.cross_a_to_b == D("27.35") * D("0.25")
    pending = result.pending_carry_forwards
    assert len(pending) == 1
    assert pending[0].basket == "A"
    assert pending[0].origin_year == 2022
    assert pending[0].expiry_year == 2026


def test_sorting_order_does_not_affect_result():
    """summaries passed in reverse order should yield the same result."""
    summaries_fwd = [
        YearlyBaseSummary(2022, D("-100"), D("40")),
        YearlyBaseSummary(2023, D("80"), D("30")),
    ]
    summaries_rev = list(reversed(summaries_fwd))

    result_fwd = calculate_compensation(summaries_fwd)
    result_rev = calculate_compensation(summaries_rev)

    for r1, r2 in zip(result_fwd.yearly_results, result_rev.yearly_results):
        assert r1.year == r2.year
        assert r1.net_basket_a == r2.net_basket_a
        assert r1.net_basket_b == r2.net_basket_b
