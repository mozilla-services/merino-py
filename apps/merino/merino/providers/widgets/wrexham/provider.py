"""Provider for the Wrexham widget endpoints."""

from datetime import UTC, datetime

from merino.cache.protocol import CacheAdapter
from merino.providers.widgets.wrexham.mock_data import (
    CHAMPIONSHIP,
    build_mock_matches,
    build_mock_standings,
)
from merino.providers.widgets.wrexham.protocol import MatchesResponse, StandingsResponse


class WrexhamProvider:
    """Serves Wrexham matches and EFL Championship standings to the widget."""

    mock_data_enabled: bool
    cache: CacheAdapter | None

    def __init__(self, mock_data_enabled: bool, cache: CacheAdapter | None = None) -> None:
        self.mock_data_enabled = mock_data_enabled
        self.cache = cache

    async def get_matches(self, limit: int) -> MatchesResponse:
        """Return previous, current and upcoming matches.

        `limit` caps the number of previous and upcoming matches.
        """
        if not self.mock_data_enabled:
            return MatchesResponse(previous=[], current=[], upcoming=[])

        matches = build_mock_matches(datetime.now(UTC).replace(microsecond=0))
        return MatchesResponse(
            previous=matches.previous[:limit],
            current=matches.current,
            upcoming=matches.upcoming[:limit],
        )

    async def get_standings(self) -> StandingsResponse:
        """Return the EFL Championship table."""
        if not self.mock_data_enabled:
            return StandingsResponse(competition=CHAMPIONSHIP, standings=[])

        return build_mock_standings()

    async def shutdown(self) -> None:
        """Release resources held by the provider.
        """
        if self.cache is not None:
            await self.cache.close()
