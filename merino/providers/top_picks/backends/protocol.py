"""Protocol for the Top Picks provider backend."""
from collections import defaultdict
from typing import Protocol

from pydantic import BaseModel


class TopPicksData(BaseModel):
    """Class that holds Top Pick Suggestion Content."""

    primary_index: defaultdict[str, list[int]]
    secondary_index: defaultdict[str, list[int]]
    short_domain_index: defaultdict[str, list[int]]
    results: list[dict]
    query_min: int
    query_max: int
    query_char_limit: int
    firefox_char_limit: int


class TopPicksBackend(Protocol):
    """Protocol for Top Picks backend that the provider depends on."""

    generation: int

    async def fetch(self) -> TopPicksData:  # pragma: no cover
        """Fetch Top Picks suggestions from domain list.

        Raises:
            BackendError: If the top picks data is unavailable.
        """
        ...
