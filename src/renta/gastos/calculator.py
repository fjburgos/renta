"""Calculate deductions for gastos deducibles (Comunitat Valenciana, IRPF 2025)."""

from __future__ import annotations

from decimal import Decimal

from renta.gastos.categories import (
    CATEGORY_RULES,
    Beneficiary,
    CategoryRule,
    DeclarationType,
    DeductionCategory,
    PaymentMethod,
)
from renta.gastos.models import ContributorConfig, DeduccionResult, ExpenseEntry

_ZERO = Decimal("0")
_ONE = Decimal("1")


def calculate_deductions(
    expenses: list[ExpenseEntry],
    config: ContributorConfig,
) -> list[DeduccionResult]:
    """Return a DeduccionResult per category that has at least one expense entry."""
    results = []
    categories_present = {e.category for e in expenses}

    for category in categories_present:
        rule = CATEGORY_RULES[category]
        entries = [e for e in expenses if e.category == category]
        result = _calculate_category(entries, rule, config)
        results.append(result)

    return sorted(results, key=lambda r: r.category.value)


def _calculate_category(
    entries: list[ExpenseEntry],
    rule: CategoryRule,
    config: ContributorConfig,
) -> DeduccionResult:
    warnings: list[str] = []

    valid_entries, invalid_entries = _split_by_payment_validity(entries)
    for e in invalid_entries:
        warnings.append(
            f"{e.date} — {e.description}: pago en efectivo no es válido para esta deducción."
        )

    for e in valid_entries:
        if not e.has_invoice:
            warnings.append(f"{e.date} — {e.description}: falta factura o recibo.")
        if not e.has_payment_proof:
            warnings.append(f"{e.date} — {e.description}: falta justificante de pago.")

    if rule.category == DeductionCategory.MATERIAL_ESCOLAR and not config.contribuyente_en_paro:
        warnings.append(
            "Deducción material escolar requiere que el contribuyente esté en desempleo "
            "e inscrito como demandante de empleo. No se aplica."
        )
        return _zero_result(rule, len(entries), _sum_amounts(entries), warnings)

    total = _sum_amounts(valid_entries)
    rate = _effective_rate(rule, config)

    if rule.fixed_amount:
        # For fixed-amount deductions the deduction equals the capped sum, not rate × expenses
        person_count = _count_eligible_persons(valid_entries, rule)
        annual_limit = rule.annual_limit * person_count
        gross = min(total, annual_limit)
    else:
        person_count = _count_eligible_persons(valid_entries, rule)
        annual_limit = rule.annual_limit * person_count
        gross = total * rate
        gross = min(gross, annual_limit)

    income_factor = _income_factor(rule, config)
    final = (gross * income_factor).quantize(Decimal("0.01"))

    return DeduccionResult(
        category=rule.category,
        description=rule.description,
        expense_count=len(entries),
        total_expenses=total,
        deduction_gross=total * rate if not rule.fixed_amount else gross,
        deduction_capped=gross,
        deduction_final=final,
        income_factor=income_factor,
        warnings=warnings,
    )


def _split_by_payment_validity(
    entries: list[ExpenseEntry],
) -> tuple[list[ExpenseEntry], list[ExpenseEntry]]:
    valid = [e for e in entries if e.payment_method != PaymentMethod.EFECTIVO]
    invalid = [e for e in entries if e.payment_method == PaymentMethod.EFECTIVO]
    return valid, invalid


def _sum_amounts(entries: list[ExpenseEntry]) -> Decimal:
    return sum((e.amount for e in entries), _ZERO)


def _effective_rate(rule: CategoryRule, config: ContributorConfig) -> Decimal:
    if rule.category != DeductionCategory.DEPORTE_SALUDABLE:
        return rule.rate or _ZERO
    if config.disability_pct >= 65 or config.age >= 75:
        return _ONE
    if config.disability_pct >= 33 or config.age >= 65:
        return Decimal("0.50")
    return Decimal("0.30")


def _count_eligible_persons(entries: list[ExpenseEntry], rule: CategoryRule) -> int:
    """Return multiplier for per-person limits."""
    if not rule.limit_per_person:
        return 1
    # Count distinct descendientes + 1 per non-descendant beneficiary
    beneficiaries = {e.beneficiary for e in entries}
    descendant_entries = [e for e in entries if e.beneficiary == Beneficiary.DESCENDIENTE]
    # Use notes field convention "descendiente_1", "descendiente_2" to count distinct children
    distinct_descendants = len(
        {e.notes.split("|")[0].strip() for e in descendant_entries if e.notes}
    )
    non_descendants = len([b for b in beneficiaries if b != Beneficiary.DESCENDIENTE])
    return max(1, distinct_descendants + non_descendants)


def _income_factor(rule: CategoryRule, config: ContributorConfig) -> Decimal:
    t = rule.renta_threshold
    if config.declaration_type == DeclarationType.CONJUNTA:
        limit_full = t.limit_full_conjunta
        limit_max = t.limit_max_conjunta
    else:
        limit_full = t.limit_full
        limit_max = t.limit_max

    base = config.base_total
    if base <= limit_full:
        return _ONE
    if base >= limit_max:
        return _ZERO
    if limit_max == limit_full:
        return _ZERO
    factor = _ONE - (base - limit_full) / (limit_max - limit_full)
    return factor.quantize(Decimal("0.0001"))


def _zero_result(
    rule: CategoryRule, count: int, total: Decimal, warnings: list[str]
) -> DeduccionResult:
    return DeduccionResult(
        category=rule.category,
        description=rule.description,
        expense_count=count,
        total_expenses=total,
        deduction_gross=_ZERO,
        deduction_capped=_ZERO,
        deduction_final=_ZERO,
        income_factor=_ZERO,
        warnings=warnings,
    )
