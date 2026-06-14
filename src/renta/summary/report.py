"""Summary report: which casillas to fill and with what amounts."""

from __future__ import annotations

import datetime
import functools
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import jinja2

_ZERO = Decimal("0")
_TWO = Decimal("2")


@dataclass(frozen=True)
class GastosContributor:
    source_name: str
    total_deducible: Decimal


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(amount: Decimal) -> str:
    return _fmt(amount) + " €"


def _half(amount: Decimal) -> Decimal:
    return (amount / _TWO).quantize(Decimal("0.01"))


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
    env.filters["half"] = _half
    env.filters["ljust"] = _ljust
    env.filters["rjust"] = _rjust
    return env


def build_report(
    tax_year: int,
    *,
    net_basket_a: Decimal | None = None,
    gross_basket_a: Decimal | None = None,
    dividends_gross: Decimal | None = None,
    dividends_dii: Decimal | None = None,
    cuentas_gross: Decimal | None = None,
    net_basket_b: Decimal | None = None,
    gastos: list[GastosContributor] | None = None,
) -> str:
    """Render the summary report for *tax_year* from available module results."""
    net_a = net_basket_a if net_basket_a is not None else _ZERO
    gross_a = gross_basket_a if gross_basket_a is not None else _ZERO
    div_gross = dividends_gross if dividends_gross is not None else _ZERO
    div_dii = dividends_dii if dividends_dii is not None else _ZERO
    cuentas = cuentas_gross if cuentas_gross is not None else _ZERO
    net_b = net_basket_b if net_basket_b is not None else _ZERO

    casilla_0380 = net_a if net_a >= _ZERO else _ZERO
    casilla_0390 = abs(net_a) if net_a < _ZERO else _ZERO

    template = _make_jinja_env().get_template("report.txt.j2")
    return template.render(
        tax_year=tax_year,
        today=datetime.date.today().strftime("%d/%m/%Y"),
        has_etfs=gross_basket_a is not None,
        has_dividends=dividends_gross is not None,
        has_cuentas=cuentas_gross is not None,
        has_compensation=net_basket_a is not None,
        gross_basket_a=gross_a,
        casilla_0380=casilla_0380,
        casilla_0390=casilla_0390,
        net_basket_a=net_a,
        div_gross=div_gross,
        div_dii=div_dii,
        cuentas=cuentas,
        net_basket_b=net_b,
        gastos=gastos or [],
    )
