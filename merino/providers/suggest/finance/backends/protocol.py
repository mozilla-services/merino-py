"""Protocol for finance provider backends."""

from typing import Protocol
from merino.providers.suggest.finance.backends.polygon.utils import FinanceEntityType, TickerSymbol


class FinanceContext:
    """Model that contains context from the finance suggestion request needed to make finance report."""

    entity_type: FinanceEntityType
    ticker_symbol: TickerSymbol
    # TODO might change
    request_type: str = "price" or "aggregate"


class FinanceReport:
    """Model for finance report that is returned as part of the finance suggestion response"""

    entity_type: FinanceEntityType
    ticker_symbol: TickerSymbol
    price: float


class FinanceBackend(Protocol):
    """Protocol for a finance backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_finance_report(
        self, finance_context: FinanceContext
    ) -> FinanceReport | None:  # pragma: no cover
        """Get finance information from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
