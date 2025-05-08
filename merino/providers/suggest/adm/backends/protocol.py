"""Protocol for the AdM provider backends."""

from typing import Any, Protocol
from pydantic import BaseModel


class SuggestionContent(BaseModel):
    """Class that holds subset of results from a fetch operation."""

    core_suggestions_data: dict[int, dict[str, Any]] = {}
    overrides: dict[int, dict[str, Any]] = {}
    full_keywords: dict[str, list] = {}
    results: dict[str, tuple[int, int]] = {}

class GlobalSuggestionContent(BaseModel):
    """Class that holds all results from a fetch operation."""

    suggestion_content: dict[str, SuggestionContent]
    icons: dict[str, str] = {}


class AdmBackend(Protocol):
    """Protocol for an AdM backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def fetch(self) -> GlobalSuggestionContent:  # pragma: no cover
        """Get suggestion content from partner."""
        ...
