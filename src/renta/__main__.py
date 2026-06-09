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
    if "etfs" in config:
        _run_etfs(config["etfs"], base_path)
        ran_any = True
    if "dividends" in config:
        _run_dividends(config["dividends"], base_path)
        ran_any = True
    if "cuentas" in config:
        _run_cuentas(config["cuentas"], base_path)
        ran_any = True

    if not ran_any:
        print("Error: no se encontró ninguna sección de cálculo en la configuración.", file=sys.stderr)
        sys.exit(1)


def _run_etfs(cfg: dict[str, Any], base_path: Path) -> None:
    from renta.etfs import calculate, calculate_all_years

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
            return
        for yr, report in reports.items():
            out = output_dir / f"informe_acciones_{yr}.txt"
            out.write_text(report, encoding="utf-8")
            print(f"Informe ETFs {yr} guardado en: {out}")


def _run_dividends(cfg: dict[str, Any], base_path: Path) -> None:
    from renta.dividends import calculate, calculate_all_years

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
            return
        for yr, report in reports.items():
            out = output_dir / f"informe_dividendos_{yr}.txt"
            out.write_text(report, encoding="utf-8")
            print(f"Informe dividendos {yr} guardado en: {out}")


def _run_cuentas(cfg: dict[str, Any], base_path: Path) -> None:
    from renta.cuentas import calculate, calculate_all_years

    # Accept 'input' as a single string or a YAML list, and 'inputs' as a list.
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
