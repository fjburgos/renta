"""Deduction categories and their calculation rules for Comunitat Valenciana IRPF 2025."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class DeductionCategory(StrEnum):
    DEPORTE_SALUDABLE = "deporte_saludable"
    SALUD_BUCODENTAL = "salud_bucodental"
    SALUD_MENTAL = "salud_mental"
    OPTICA = "optica"
    ENFERMEDAD_CRONICA = "enfermedad_cronica"
    FORMACION_MUSICAL = "formacion_musical"
    ABONOS_CULTURALES = "abonos_culturales"
    GUARDERIA = "guarderia"
    MATERIAL_ESCOLAR = "material_escolar"


class PaymentMethod(StrEnum):
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"
    CHEQUE = "cheque"
    INGRESO = "ingreso"
    EFECTIVO = "efectivo"  # not valid for any deduction


class Beneficiary(StrEnum):
    CONTRIBUYENTE = "contribuyente"
    CONYUGE = "conyuge"
    DESCENDIENTE = "descendiente"


class DeclarationType(StrEnum):
    INDIVIDUAL = "individual"
    CONJUNTA = "conjunta"


@dataclass(frozen=True)
class RentaThreshold:
    """Income limits for a deduction type."""

    limit_full: Decimal       # below this: full deduction
    limit_max: Decimal        # above this: zero deduction
    limit_full_conjunta: Decimal
    limit_max_conjunta: Decimal


@dataclass(frozen=True)
class CategoryRule:
    """Calculation rule for a single deduction category."""

    category: DeductionCategory
    description: str
    # None means the rate varies (e.g. deporte depends on age/disability)
    rate: Decimal | None
    annual_limit: Decimal
    # True when the limit applies per eligible person, not per contributor
    limit_per_person: bool
    renta_threshold: RentaThreshold
    # True when the deduction is a fixed amount (not rate × expense)
    fixed_amount: bool = False


# ── Renta thresholds ──────────────────────────────────────────────────────────

_THRESHOLD_STANDARD = RentaThreshold(
    limit_full=Decimal("54000"),
    limit_max=Decimal("60000"),
    limit_full_conjunta=Decimal("72000"),
    limit_max_conjunta=Decimal("78000"),
)

_THRESHOLD_REDUCED = RentaThreshold(
    limit_full=Decimal("27000"),
    limit_max=Decimal("30000"),
    limit_full_conjunta=Decimal("44000"),
    limit_max_conjunta=Decimal("47000"),
)

_THRESHOLD_CULTURAL = RentaThreshold(
    limit_full=Decimal("50000"),
    limit_max=Decimal("50000"),
    limit_full_conjunta=Decimal("50000"),
    limit_max_conjunta=Decimal("50000"),
)

# ── Rules ─────────────────────────────────────────────────────────────────────

CATEGORY_RULES: dict[DeductionCategory, CategoryRule] = {
    DeductionCategory.DEPORTE_SALUDABLE: CategoryRule(
        category=DeductionCategory.DEPORTE_SALUDABLE,
        description="Deporte y actividades saludables",
        rate=None,  # determined by age/disability: 30%, 50%, or 100%
        annual_limit=Decimal("150"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
    ),
    DeductionCategory.SALUD_BUCODENTAL: CategoryRule(
        category=DeductionCategory.SALUD_BUCODENTAL,
        description="Salud bucodental (no estética)",
        rate=Decimal("0.30"),
        annual_limit=Decimal("150"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
    ),
    DeductionCategory.SALUD_MENTAL: CategoryRule(
        category=DeductionCategory.SALUD_MENTAL,
        description="Salud mental (psicólogo clínico, psiquiatra)",
        rate=Decimal("0.30"),
        annual_limit=Decimal("150"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
    ),
    DeductionCategory.OPTICA: CategoryRule(
        category=DeductionCategory.OPTICA,
        description="Lentes graduadas / lentes de contacto",
        rate=Decimal("0.30"),
        annual_limit=Decimal("100"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
    ),
    DeductionCategory.ENFERMEDAD_CRONICA: CategoryRule(
        category=DeductionCategory.ENFERMEDAD_CRONICA,
        description="Enfermedades crónicas complejas, raras, daño cerebral, Alzheimer",
        rate=Decimal("1.00"),
        annual_limit=Decimal("100"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
        fixed_amount=True,
    ),
    DeductionCategory.FORMACION_MUSICAL: CategoryRule(
        category=DeductionCategory.FORMACION_MUSICAL,
        description="Formación musical (conservatorio, escuela inscrita CV)",
        rate=Decimal("1.00"),
        annual_limit=Decimal("150"),
        limit_per_person=False,
        renta_threshold=_THRESHOLD_STANDARD,
    ),
    DeductionCategory.ABONOS_CULTURALES: CategoryRule(
        category=DeductionCategory.ABONOS_CULTURALES,
        description="Abonos culturales (Abono Cultural Valenciano — Culturarts)",
        rate=Decimal("0.21"),
        annual_limit=Decimal("34.65"),  # 21% × 165 €
        limit_per_person=False,
        renta_threshold=_THRESHOLD_CULTURAL,
    ),
    DeductionCategory.GUARDERIA: CategoryRule(
        category=DeductionCategory.GUARDERIA,
        description="Guardería / 1er ciclo infantil (< 3 años)",
        rate=Decimal("0.15"),
        annual_limit=Decimal("297"),
        limit_per_person=True,  # 297 € per eligible child
        renta_threshold=_THRESHOLD_REDUCED,
    ),
    DeductionCategory.MATERIAL_ESCOLAR: CategoryRule(
        category=DeductionCategory.MATERIAL_ESCOLAR,
        description="Material escolar (Primaria / ESO / Ed. Especial, solo desempleados)",
        rate=Decimal("1.00"),
        annual_limit=Decimal("110"),
        limit_per_person=True,  # 110 € per eligible child
        renta_threshold=_THRESHOLD_REDUCED,
        fixed_amount=True,
    ),
}
