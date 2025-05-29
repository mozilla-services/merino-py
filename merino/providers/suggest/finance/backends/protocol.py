"""Protocol for finance provider backends."""

from typing import Protocol


class FinanceBackend(Protocol):
    """Protocol for a finance backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    # TODO
    # async def get_something(
    #     self, finance_context: FinanceContext
    # ) -> FinanceReport | None:  # pragma: no cover
    #     """Get finance information from partner.

    #     Raises:
    #         BackendError: Category of error specific to provider backends.
    #     """
    #     ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
