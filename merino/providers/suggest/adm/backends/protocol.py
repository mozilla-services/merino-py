"""Protocol for the AdM provider backends."""

from typing import Any, Protocol

from pydantic import BaseModel


class SuggestionContent(BaseModel):
    """Class that holds the result from a fetch operation."""

    # A dictionary keyed on suggestion keywords, each value stores an index
    # (pointer) to one entry of the suggestion result list.
    suggestions: dict[tuple[str, str], tuple[int, int]]

    # A list of full keywords
    full_keywords: list[str]

    # A list of suggestion results.
    results: list[dict[str, Any]]

    # A dictionary of icon IDs to icon URLs.
    icons: dict[str, str]


class AdmBackend(Protocol):
    """Protocol for an AdM backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def fetch(self) -> SuggestionContent:  # pragma: no cover
        """Get suggestion content from partner."""
        ...
