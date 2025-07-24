"""Protocol for finance provider backends."""

from typing import Protocol, Any


class FinanceBackend(Protocol):
    """Protocol for a finance backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    # TODO types and comments
    async def get_ticker_summary(self, ticker: str) -> dict[str, Any]:  # pragma: no cover
        """Get snapshot info for a given ticker from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
