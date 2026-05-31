"""Shared fixtures for all tests."""
import datetime
from decimal import Decimal

import pytest


@pytest.fixture
def purchase_date() -> datetime.date:
    return datetime.date(2023, 3, 15)


@pytest.fixture
def sale_date() -> datetime.date:
    return datetime.date(2024, 6, 20)


@pytest.fixture
def unit_price() -> Decimal:
    return Decimal("100.00")
