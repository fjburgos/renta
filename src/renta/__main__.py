"""
CLI entry point. Invocable as:

    python -m renta [config.yaml]
    renta [config.yaml]          # after pip install -e .

If no config file is given, looks for "renta.yaml" in the current directory.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("renta.yaml")


def _load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        print(f"Error: fichero de configuración no encontrado: {config_path}", file=sys.stderr)
        sys.exit(1)
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _resolve(raw: str | None, base: Path, default: str) -> Path:
    p = Path(raw if raw is not None else default)
    return p if p.is_absolute() else base / p


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="renta",
        description="Calcula ganancias/pérdidas patrimoniales para la declaración de la renta española.",
    )
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        default=DEFAULT_CONFIG,
        help=f"Ruta al fichero YAML de configuración. Por defecto: {DEFAULT_CONFIG}",
    )
    args = parser.parse_args()

    config = _load_config(args.config)

    # base_path is relative to the config file's directory
    config_dir = args.config.resolve().parent
    raw_base = config.get("base_path", ".")
    base_path = Path(raw_base)
    if not base_path.is_absolute():
        base_path = config_dir / base_path
    base_path = base_path.resolve()

    ran_any = False
    etf_summaries: dict[int, Any] = {}
    dividend_summaries: dict[int, Any] = {}
    cuentas_summaries: dict[int, Any] = {}
    gastos_summaries: dict[int, Any] = {}
    output_dir: Path | None = None

    if "etfs" in config:
        etf_summaries, output_dir = _run_etfs(config["etfs"], base_path)
        ran_any = True
    if "dividends" in config:
        dividend_summaries, output_dir = _run_dividends(config["dividends"], base_path)
        ran_any = True
    if "cuentas" in config:
        cuentas_summaries, output_dir = _run_cuentas(config["cuentas"], base_path)
        ran_any = True
    if "gastos" in config:
        gastos_summaries, output_dir_g = _run_gastos(config["gastos"], base_path)
        if output_dir is None:
            output_dir = output_dir_g
        ran_any = True

    if not ran_any:
        print("Error: no se encontró ninguna sección de cálculo en la configuración.", file=sys.stderr)
        sys.exit(1)

    compensation_results: dict[int, Any] = {}
    if output_dir is not None and (etf_summaries or dividend_summaries or cuentas_summaries):
        compensation_results = _run_compensation(
            etf_summaries, dividend_summaries, cuentas_summaries, output_dir
        )

    if output_dir is not None:
        _run_summary(
            etf_summaries,
            dividend_summaries,
            cuentas_summaries,
            compensation_results,
            gastos_summaries,
            output_dir,
        )


def _run_etfs(cfg: dict[str, Any], base_path: Path) -> tuple[dict[int, Any], Path]:
    from renta.etfs import build_all_summaries, calculate, calculate_all_years
    from renta.etfs.report import TaxSummary

    input_path = _resolve(cfg.get("input"), base_path, "data/input/degiro/Transactions.xlsx")
    output_dir = _resolve(cfg.get("output_dir"), base_path, "data/output")
    year: int | None = cfg.get("year")

    if not input_path.exists():
        print(f"Error: fichero no encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(exist_ok=True, parents=True)

    if year is not None:
        report = calculate(input_path, year)
        out = output_dir / f"informe_acciones_{year}.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Informe ETFs guardado en: {out}")
    else:
        reports = calculate_all_years(input_path)
        if not reports:
            print("No se encontraron ventas en el fichero.")
            return {}, output_dir
        for yr, report in reports.items():
            out = output_dir / f"informe_acciones_{yr}.txt"
            out.write_text(report, encoding="utf-8")
            print(f"Informe ETFs {yr} guardado en: {out}")

    all_summaries: dict[int, TaxSummary] = build_all_summaries(input_path)
    return all_summaries, output_dir


def _run_dividends(cfg: dict[str, Any], base_path: Path) -> tuple[dict[int, Any], Path]:
    from renta.dividends import build_all_summaries, calculate, calculate_all_years
    from renta.dividends.models import DividendSummary

    input_path = _resolve(cfg.get("input"), base_path, "data/input/degiro/Account.xlsx")
    output_dir = _resolve(cfg.get("output_dir"), base_path, "data/output")
    year: int | None = cfg.get("year")
    fx_overrides = _parse_fx_overrides(cfg.get("fx_overrides") or [])

    if not input_path.exists():
        print(f"Error: fichero no encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(exist_ok=True, parents=True)

    if year is not None:
        report = calculate(input_path, year, fx_overrides=fx_overrides or None)
        out = output_dir / f"informe_dividendos_{year}.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Informe dividendos guardado en: {out}")
    else:
        reports = calculate_all_years(input_path, fx_overrides=fx_overrides or None)
        if not reports:
            print("No se encontraron dividendos en el fichero.")
            return {}, output_dir
        for yr, report in reports.items():
            out = output_dir / f"informe_dividendos_{yr}.txt"
            out.write_text(report, encoding="utf-8")
            print(f"Informe dividendos {yr} guardado en: {out}")

    all_summaries: dict[int, DividendSummary] = build_all_summaries(
        input_path, fx_overrides=fx_overrides or None
    )
    return all_summaries, output_dir


def _run_cuentas(cfg: dict[str, Any], base_path: Path) -> tuple[dict[int, Any], Path]:
    from renta.cuentas import build_all_summaries, calculate, calculate_all_years
    from renta.cuentas.models import CuentasSummary

    raw_input = cfg.get("input")
    raw_list: list[str]
    if isinstance(raw_input, list):
        raw_list = raw_input
    elif raw_input is not None:
        raw_list = [str(raw_input)]
    else:
        raise ValueError("Se requiere 'input' en la sección 'cuentas' de la configuración.")

    output_dir = _resolve(cfg.get("output_dir"), base_path, "data/output")
    year: int | None = cfg.get("year")
    output_dir.mkdir(exist_ok=True, parents=True)

    # Aggregate cuentas summaries across all input files, merging by year.
    merged_summaries: dict[int, CuentasSummary] = {}

    for raw in raw_list:
        input_path = _resolve(raw, base_path, "")
        if not input_path.exists():
            print(f"Error: fichero no encontrado: {input_path}", file=sys.stderr)
            sys.exit(1)

        if year is not None:
            report = calculate(input_path, year)
            out = output_dir / f"informe_cuentas_{year}_{input_path.stem}.txt"
            out.write_text(report, encoding="utf-8")
            print(f"Informe cuentas guardado en: {out}")
        else:
            reports = calculate_all_years(input_path)
            if not reports:
                print(f"No se encontraron datos de cuentas en: {input_path.name}")
                continue
            for yr, report in reports.items():
                out = output_dir / f"informe_cuentas_{yr}_{input_path.stem}.txt"
                out.write_text(report, encoding="utf-8")
                print(f"Informe cuentas {yr} guardado en: {out}")

        file_summaries = build_all_summaries(input_path)
        for yr, s in file_summaries.items():
            if yr in merged_summaries:
                existing = merged_summaries[yr]
                merged_summaries[yr] = CuentasSummary(
                    tax_year=yr,
                    accounts=existing.accounts + s.accounts,
                    total_gross_eur=existing.total_gross_eur + s.total_gross_eur,
                    total_fees_eur=existing.total_fees_eur + s.total_fees_eur,
                    total_net_eur=existing.total_net_eur + s.total_net_eur,
                    total_tax_withheld_eur=existing.total_tax_withheld_eur + s.total_tax_withheld_eur,
                )
            else:
                merged_summaries[yr] = s

    return merged_summaries, output_dir


def _run_compensation(
    etf_summaries: dict[int, Any],
    dividend_summaries: dict[int, Any],
    cuentas_summaries: dict[int, Any],
    output_dir: Path,
) -> dict[int, Any]:
    from decimal import Decimal

    from renta.compensation import build_report, calculate_compensation
    from renta.compensation.models import YearlyBaseSummary

    all_years = sorted(
        etf_summaries.keys() | dividend_summaries.keys() | cuentas_summaries.keys()
    )
    if not all_years:
        return {}

    _ZERO = Decimal("0")

    yearly_summaries: list[YearlyBaseSummary] = []
    for yr in all_years:
        etf = etf_summaries.get(yr)
        div = dividend_summaries.get(yr)
        cuentas = cuentas_summaries.get(yr)

        net_a = etf.net_result if etf is not None else _ZERO
        net_b = (div.total_gross if div is not None else _ZERO) + (
            cuentas.total_gross_eur if cuentas is not None else _ZERO
        )
        yearly_summaries.append(YearlyBaseSummary(year=yr, net_capital_gains=net_a, net_capital_income=net_b))

    result = calculate_compensation(yearly_summaries)

    yearly_by_year: dict[int, Any] = {r.year: r for r in result.yearly_results}

    for yr in all_years:
        report = build_report(result, yr)
        out = output_dir / f"informe_compensacion_{yr}.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Informe compensación {yr} guardado en: {out}")

    return yearly_by_year


def _run_gastos(cfg: dict[str, Any], base_path: Path) -> tuple[dict[int, Any], Path]:
    from decimal import Decimal

    from renta.gastos import build_report, calculate_deductions, read_gastos_excel
    from renta.summary import GastosContributor

    raw_input = cfg.get("input")
    if raw_input is None:
        print("Error: se requiere 'input' en la sección 'gastos' de la configuración.", file=sys.stderr)
        sys.exit(1)
    raw_list: list[str] = raw_input if isinstance(raw_input, list) else [str(raw_input)]

    year: int | None = cfg.get("year")
    if year is None:
        print("Error: se requiere 'year' en la sección 'gastos' de la configuración.", file=sys.stderr)
        sys.exit(1)

    output_dir = _resolve(cfg.get("output_dir"), base_path, "data/output")
    output_dir.mkdir(exist_ok=True, parents=True)

    contributors: list[GastosContributor] = []

    for raw in raw_list:
        input_path = _resolve(raw, base_path, "")
        if not input_path.exists():
            print(f"Error: fichero no encontrado: {input_path}", file=sys.stderr)
            sys.exit(1)

        contributor_config, expenses = read_gastos_excel(input_path)
        results = calculate_deductions(expenses, contributor_config)
        report = build_report(input_path, contributor_config, results, year)

        out = output_dir / f"informe_gastos_{year}_{input_path.stem}.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Informe gastos guardado en: {out}")

        active = [r for r in results if r.expense_count > 0]
        total_deducible = sum((r.deduction_final for r in active), Decimal("0"))
        contributors.append(GastosContributor(source_name=input_path.stem, total_deducible=total_deducible))

    return {year: contributors}, output_dir


def _run_summary(
    etf_summaries: dict[int, Any],
    dividend_summaries: dict[int, Any],
    cuentas_summaries: dict[int, Any],
    compensation_results: dict[int, Any],
    gastos_summaries: dict[int, Any],
    output_dir: Path,
) -> None:
    from renta.summary import build_report as build_summary_report

    all_years = sorted(
        etf_summaries.keys()
        | dividend_summaries.keys()
        | cuentas_summaries.keys()
        | gastos_summaries.keys()
    )
    for yr in all_years:
        etf = etf_summaries.get(yr)
        div = dividend_summaries.get(yr)
        cuentas = cuentas_summaries.get(yr)
        comp = compensation_results.get(yr)
        gastos_contributors = gastos_summaries.get(yr) or []

        report = build_summary_report(
            yr,
            net_basket_a=comp.net_basket_a if comp is not None else None,
            gross_basket_a=etf.net_result if etf is not None else None,
            dividends_gross=div.total_gross if div is not None else None,
            dividends_dii=div.total_deductible_foreign_tax if div is not None else None,
            cuentas_gross=cuentas.total_gross_eur if cuentas is not None else None,
            net_basket_b=comp.net_basket_b if comp is not None else None,
            gastos=gastos_contributors,
        )
        out = output_dir / f"informe_resumen_{yr}.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Informe resumen {yr} guardado en: {out}")


def _parse_fx_overrides(entries: list[Any]) -> dict[tuple[str, datetime.date], Decimal]:
    overrides: dict[tuple[str, datetime.date], Decimal] = {}
    for entry in entries:
        isin: str = str(entry["isin"])
        date = datetime.date.fromisoformat(str(entry["date"]))
        rate = Decimal(str(entry["rate"]))
        overrides[(isin, date)] = rate
    return overrides


if __name__ == "__main__":
    main()
