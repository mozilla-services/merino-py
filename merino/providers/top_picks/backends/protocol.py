"""Protocol for the Top Picks provider backend."""
from collections import defaultdict
from typing import Protocol

from pydantic import BaseModel


class TopPicksData(BaseModel):
    """Class that holds Top Pick Suggestion Content."""

    primary_index: defaultdict
    secondary_index: defaultdict
    short_domain_index: defaultdict
    results: list[dict]
    index_char_range: tuple[int, int]
    query_char_limit: int
    firefox_char_limit: int


class TopPicksBackend(Protocol):
    """Protocol for Top Picks backend that the provider depends on."""

    async def fetch(self) -> TopPicksData:  # pragma: no cover
        """Fetch Top Picks suggestions from domain list."""
        ...
