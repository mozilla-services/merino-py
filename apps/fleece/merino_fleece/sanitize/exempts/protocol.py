"""Protocol for search term sanitization exempts."""

from typing import Protocol


class SanitizationExempt(Protocol):
    """Protocol class for search term sanitization exempt."""

    async def initialize(self) -> None:  # pragma: no cover
        """Bootstrap the sanitization exempt."""
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down the sanitization exempt."""
        ...

    def is_exempt(self, search_term: str) -> bool:  # pragma: no cover
        """Return whether a given search term is exempt from sanitization.

        Args:
          - `search_term`: the search term.
        """
        ...
