"""Data models for gastos deducibles module."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from renta.gastos.categories import Beneficiary, DeclarationType, DeductionCategory, PaymentMethod


@dataclass(frozen=True)
class ExpenseEntry:
    """A single deductible expense as entered in the Excel."""

    date: datetime.date
    category: DeductionCategory
    description: str
    provider: str
    provider_nif: str
    amount: Decimal
    payment_method: PaymentMethod
    beneficiary: Beneficiary
    has_invoice: bool
    has_payment_proof: bool
    notes: str = ""


@dataclass(frozen=True)
class ContributorConfig:
    """Taxpayer configuration for the fiscal year."""

    base_liquidable_general: Decimal
    base_liquidable_ahorro: Decimal
    declaration_type: DeclarationType
    age: int
    disability_pct: int = 0          # 0 if no disability
    has_familia_numerosa: bool = False
    contribuyente_en_paro: bool = False

    @property
    def base_total(self) -> Decimal:
        return self.base_liquidable_general + self.base_liquidable_ahorro


@dataclass
class DeduccionResult:
    """Calculated deduction for a single category."""

    category: DeductionCategory
    description: str
    expense_count: int
    total_expenses: Decimal
    deduction_gross: Decimal       # before annual limit
    deduction_capped: Decimal      # after annual limit
    deduction_final: Decimal       # after income reduction factor
    income_factor: Decimal         # 1.0 = no reduction; 0.0 = fully phased out
    warnings: list[str] = field(default_factory=list)
