"""Domain-specific exceptions for the renta package."""


class ParseError(Exception):
    """Raised when an input file row contains invalid or missing data."""


class NegativeStockError(Exception):
    """Raised when the FIFO engine detects more shares sold than available in the lot queue."""


class WashSaleConfigError(Exception):
    """Raised when the wash-sale rule receives incoherent configuration."""


class FxRateUnavailableError(Exception):
    """Raised when no ECB exchange rate is found for a given currency and date."""
