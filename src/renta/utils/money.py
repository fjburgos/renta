"""Decimal arithmetic helpers. All monetary amounts must use Decimal, never float."""

from decimal import ROUND_HALF_UP, Decimal

from renta.utils.exceptions import ParseError

_TWO_PLACES = Decimal("0.01")


def round_eur(amount: Decimal) -> Decimal:
    """Round to 2 decimal places using ROUND_HALF_UP. Use only in the presentation layer."""
    return amount.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def to_decimal(value: str | float | int | None) -> Decimal:
    """Convert any numeric input value to a clean Decimal. Raises ParseError if value is None."""
    if value is None:
        raise ParseError(f"Expected a numeric value, got None")
    return Decimal(str(value))


def to_decimal_or_zero(value: str | float | int | None) -> Decimal:
    """Like to_decimal but returns Decimal('0') when value is None."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))
