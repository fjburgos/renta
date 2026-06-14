"""Text report for gastos deducibles calculation."""

from __future__ import annotations

import functools
from decimal import Decimal
from pathlib import Path

import jinja2

from renta.gastos.models import ContributorConfig, DeduccionResult

_ZERO = Decimal("0")


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(amount: Decimal) -> str:
    return _fmt(amount) + " €"


def _ljust(s: object, width: int) -> str:
    return str(s).ljust(width)


def _rjust(s: object, width: int) -> str:
    return str(s).rjust(width)


@functools.cache
def _make_jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    env.filters["fmt"] = _fmt
    env.filters["eur"] = _eur
    env.filters["ljust"] = _ljust
    env.filters["rjust"] = _rjust
    return env


def build_report(
    source_path: Path,
    config: ContributorConfig,
    results: list[DeduccionResult],
    year: int,
) -> str:
    active = [r for r in results if r.expense_count > 0]
    total_deducible = sum((r.deduction_final for r in active), _ZERO)
    all_warnings = [w for r in active for w in r.warnings]

    template = _make_jinja_env().get_template("report.txt.j2")
    return template.render(
        year=year,
        source_name=source_path.name,
        config=config,
        active=active,
        total_deducible=total_deducible,
        all_warnings=all_warnings,
    )
