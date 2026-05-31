from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from renta.utils.exceptions import FxRateUnavailableError

_ECB_ZIP_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
_ECB_CSV_NAME = "eurofxref-hist.csv"
_LOOKBACK_DAYS = 5  # handles weekends and bank holidays


class FxRatesProvider(Protocol):
    def get_rate(self, currency: str, on_date: date) -> Decimal: ...


class ECBRatesProvider:
    """Downloads and caches the full ECB historical FX rates on first use.

    Rates are in units of foreign currency per 1 EUR (e.g. USD=1.0897 means 1 EUR = 1.0897 USD).
    To convert a foreign amount to EUR: amount_eur = amount_foreign / rate.
    """

    def __init__(self) -> None:
        self._rates: dict[tuple[date, str], Decimal] | None = None

    def _ensure_loaded(self) -> None:
        if self._rates is not None:
            return
        with urllib.request.urlopen(_ECB_ZIP_URL) as response:
            raw = response.read()
        rates: dict[tuple[date, str], Decimal] = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            with zf.open(_ECB_CSV_NAME) as csv_file:
                reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
                for row in reader:
                    date_str = (row.get("Date") or "").strip()
                    if not date_str:
                        continue
                    try:
                        row_date = date.fromisoformat(date_str)
                    except ValueError:
                        continue
                    for col, val in row.items():
                        if not col or col == "Date" or not val or not val.strip():
                            continue
                        try:
                            rates[(row_date, col.strip())] = Decimal(val.strip())
                        except Exception:
                            pass
        self._rates = rates

    def get_rate(self, currency: str, on_date: date) -> Decimal:
        self._ensure_loaded()
        assert self._rates is not None
        for delta in range(_LOOKBACK_DAYS):
            candidate = on_date - timedelta(days=delta)
            if (candidate, currency) in self._rates:
                return self._rates[(candidate, currency)]
        raise FxRateUnavailableError(
            f"No ECB rate for {currency} on {on_date} (checked {_LOOKBACK_DAYS} preceding days)"
        )
