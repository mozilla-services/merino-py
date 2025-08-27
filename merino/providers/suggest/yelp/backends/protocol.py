"""Protocol for yelp provider backends."""

from typing import Protocol


class YelpBackendProtocol(Protocol):
    """Protocol for a yelp backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...

    async def get_business(self, search_term, location) -> dict | None:
        """Return Yelp business."""
        ...
