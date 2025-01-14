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
        """Search Wikipedia and return articles relevant to the given query.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...
