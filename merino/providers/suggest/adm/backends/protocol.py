"""Protocol for the AdM provider backends."""

from typing import Any, Protocol

from pydantic import BaseModel

SegmentTuple = tuple[str, ...]


class SuggestionContent(BaseModel):
    """Class that holds the result from a fetch operation."""

    # A dictionary keyed on suggestion id each value stores
    # common fields data across segments
    core_suggestions_data: dict[int, dict[str, Any]] = {}
    # A dictionary keyed on suggestion id and segment,
    # each value stores fields data that is different across segments
    variants: dict[int, dict[SegmentTuple, Any]] = {}
    # A list of full keywords
    full_keywords: list[str] = []
    # A list of suggestion results
    results: dict[SegmentTuple, dict[str, tuple[int, int]]] = {}


class GlobalSuggestionContent(BaseModel):
    """Class that holds all results from a fetch operation."""

    suggestion_content: dict[str, SuggestionContent]
    icons: dict[str, str]


class AdmBackend(Protocol):
    """Protocol for an AdM backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def fetch(self) -> GlobalSuggestionContent:  # pragma: no cover
        """Get suggestion content from partner."""
        ...
