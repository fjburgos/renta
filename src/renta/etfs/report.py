"""
Tax report generator for capital gains from ETFs and stocks.

Produces a plain-text report with the data needed to complete the Spanish IRPF
declaration manually via the AEAT Renta Web portal.

Casilla references are from the IRPF 2023 model (Modelo 100).
Verify the exact casilla numbers against the official model for the relevant tax year,
as they may change annually.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import jinja2

from renta.etfs.models import CapitalGainEvent, WashSaleRecord
from renta.utils.money import round_eur

# ── IRPF 2023 casilla references ─────────────────────────────────────────────
# These numbers apply to Renta 2023 (filed in 2024). Verify for other years.
CASILLA_GAINS = "0380"  # Saldo positivo de G/P patrimoniales — base del ahorro
CASILLA_LOSSES = "0390"  # Saldo negativo de G/P patrimoniales — base del ahorro

# Tax brackets for the base imponible del ahorro (Art. 66 LIRPF, updated PGE 2021)
_AHORRO_BRACKETS = [
    (Decimal("6000"), Decimal("0.19")),
    (Decimal("44000"), Decimal("0.21")),  # 6001–50000
    (Decimal("150000"), Decimal("0.23")),  # 50001–200000
    (Decimal("100000"), Decimal("0.27")),  # 200001–300000
    (None, Decimal("0.28")),  # over 300000
]

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
)
_jinja_env.filters["fmt"] = lambda amount: (
    f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
)
_jinja_env.filters["date_fmt"] = lambda d: d.strftime("%d/%m/%Y")


@dataclass(frozen=True)
class TaxEntry:
    """Data for one line item to be entered in Renta Web."""

    product: str
    isin: str
    acquisition_date: datetime.date
    transfer_date: datetime.date
    acquisition_value: Decimal
    transfer_value: Decimal
    reported_gain: Decimal  # after wash-sale deferral
    wash_sale_deferred: Decimal


@dataclass(frozen=True)
class TaxSummary:
    total_gains: Decimal  # sum of reported_gain > 0
    total_losses: Decimal  # sum of abs(reported_gain) where reported_gain < 0
    net_result: Decimal  # total_gains - total_losses
    total_deferred: Decimal  # wash-sale losses deferred to future years
    estimated_tax: Decimal  # informative estimate (not accounting for other income)


def build_tax_summary(
    events: list[CapitalGainEvent],
    wash_sale_records: list[WashSaleRecord],
    tax_year: int,
) -> TaxSummary:
    """Compute the TaxSummary for the given year without rendering the report."""
    entries, year_records = _year_data(events, wash_sale_records, tax_year)
    return _build_summary(entries, year_records)


def build_report(
    events: list[CapitalGainEvent],
    wash_sale_records: list[WashSaleRecord],
    tax_year: int,
) -> str:
    """
    Generate a plain-text IRPF report for the given tax year.

    Only events where transfer_date falls within tax_year are included.
    """
    entries, year_records = _year_data(events, wash_sale_records, tax_year)
    summary = _build_summary(entries, year_records)

    template = _jinja_env.get_template("report.txt.j2")
    return template.render(
        tax_year=tax_year,
        today=datetime.date.today().strftime("%d/%m/%Y"),
        casilla_gains=CASILLA_GAINS,
        casilla_losses=CASILLA_LOSSES,
        entries=entries,
        wash_sale_records=year_records,
        summary=summary,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _year_data(
    events: list[CapitalGainEvent],
    wash_sale_records: list[WashSaleRecord],
    tax_year: int,
) -> tuple[list[TaxEntry], list[WashSaleRecord]]:
    year_events = [e for e in events if e.transfer_date.year == tax_year]
    year_records = [r for r in wash_sale_records if r.loss_event.transfer_date.year == tax_year]
    return _build_entries(year_events), year_records


def _build_entries(events: list[CapitalGainEvent]) -> list[TaxEntry]:
    return [
        TaxEntry(
            product=e.product,
            isin=e.isin,
            acquisition_date=e.acquisition_date,
            transfer_date=e.transfer_date,
            acquisition_value=round_eur(e.acquisition_value),
            transfer_value=round_eur(e.transfer_value),
            reported_gain=round_eur(e.reported_gain),
            wash_sale_deferred=round_eur(e.wash_sale_deferred),
        )
        for e in events
    ]


def _build_summary(entries: list[TaxEntry], records: list[WashSaleRecord]) -> TaxSummary:
    gains = sum(
        (e.reported_gain for e in entries if e.reported_gain > Decimal("0")), Decimal("0")
    )
    losses = sum(
        (abs(e.reported_gain) for e in entries if e.reported_gain < Decimal("0")), Decimal("0")
    )
    net = gains - losses
    deferred = sum((r.deferred_loss for r in records), Decimal("0"))
    tax = _estimate_tax(net) if net > Decimal("0") else Decimal("0")

    return TaxSummary(
        total_gains=round_eur(gains),
        total_losses=round_eur(losses),
        net_result=round_eur(net),
        total_deferred=round_eur(deferred),
        estimated_tax=round_eur(tax),
    )


def _estimate_tax(net_gain: Decimal) -> Decimal:
    """Informative progressive tax estimate on the capital gains portion only."""
    tax = Decimal("0")
    remaining = net_gain
    for bracket_size, rate in _AHORRO_BRACKETS:
        if remaining <= Decimal("0"):
            break
        if bracket_size is None:
            taxable = remaining
        else:
            taxable = min(remaining, bracket_size)
        tax += taxable * rate
        remaining -= taxable
    return tax
