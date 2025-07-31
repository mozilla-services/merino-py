"""Protocol for finance provider backends."""

from typing import Protocol
from pydantic import BaseModel


class TickerSnapshot(BaseModel):
    """Ticker Snapshot."""

    todays_change_perc: str
    last_price: str


class TickerSummary(BaseModel):
    """Ticker summary."""

    ticker: str
    name: str
    last_price: str
    todays_change_perc: str
    query: str


class FinanceBackend(Protocol):
    """Protocol for a finance backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_ticker_summary(self, ticker: str) -> TickerSummary | None:  # pragma: no cover
        """Get snapshot info for a given ticker from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
