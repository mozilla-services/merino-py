"""Protocol for the Top Picks provider backend."""
from collections import defaultdict
from typing import Any, Protocol

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

    async def fetch(self) -> TopPicksData:  # pragma: no cover
        """Fetch Top Picks suggestions from domain list.

        Raises:
            BackendError: If the top picks data is unavailable.
        """
        ...


class TopPicksFileManager(Protocol):
    """Protocol for all Top Picks File managers that are local or remote.
    These deliver data for the backend to consume.
    """

    def get_file(self) -> dict[str, Any]:  # pragma: no cover
        """Get the domain data file that is passed to the backend."""
        ...
