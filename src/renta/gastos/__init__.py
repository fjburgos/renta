"""Gastos deducibles — deducciones autonómicas Comunitat Valenciana (IRPF 2025)."""

from renta.gastos.calculator import calculate_deductions
from renta.gastos.reader import read_gastos_excel
from renta.gastos.report import build_report

__all__ = ["calculate_deductions", "read_gastos_excel", "build_report"]
