"""Protocol for Dynamic Wikipedia provider backends."""

from typing import Any, Protocol


class WikipediaBackend(Protocol):
    """Protocol for a Wikipedia backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down connection to the backend"""
        ...

    async def search(self, q: str) -> list[dict[str, Any]]:  # pragma: no cover
        """Search suggestions for a given query from the backend."""
        ...
