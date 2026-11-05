"""Provider for the Wrexham widget endpoints."""

import logging
from datetime import UTC, datetime

import aiodogstatsd

from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham.mock_data import build_mock_matches, build_mock_standings
from merino.providers.widgets.wrexham.protocol import (
    CHAMPIONSHIP,
    FA_CUP,
    Match,
    MatchesResponse,
    MatchStatus,
    StandingsResponse,
)
from merino.providers.widgets.wrexham.store import WrexhamStore

logger = logging.getLogger(__name__)

PREVIOUS_STATUSES = frozenset({MatchStatus.Final, MatchStatus.Canceled})
CURRENT_STATUSES = frozenset(
    {MatchStatus.InProgress, MatchStatus.Break, MatchStatus.Delayed, MatchStatus.Suspended}
)
UPCOMING_STATUSES = frozenset({MatchStatus.Scheduled, MatchStatus.Postponed})


class WrexhamDataUnavailableError(Exception):
    """Raised when Wrexham data can't be served."""


class WrexhamProvider:
    """Serves Wrexham matches and EFL Championship standings to the widget."""

    store: WrexhamStore
    metrics_client: aiodogstatsd.Client
    mock_data_enabled: bool

    def __init__(
        self,
        store: WrexhamStore,
        metrics_client: aiodogstatsd.Client,
        mock_data_enabled: bool,
    ) -> None:
        self.store = store
        self.metrics_client = metrics_client
        self.mock_data_enabled = mock_data_enabled

    async def get_matches(self, limit: int) -> MatchesResponse:
        """Return previous, current and upcoming matches.

        `limit` caps the number of previous and upcoming matches.

        Raises:
            - `WrexhamDataUnavailableError` if the matches can't be read from Redis.
        """
        if self.mock_data_enabled:
            mock_matches = build_mock_matches(datetime.now(UTC).replace(microsecond=0))
            return MatchesResponse(
                previous=mock_matches.previous[:limit],
                current=mock_matches.current,
                upcoming=mock_matches.upcoming[:limit],
            )

        matches = await self._read_matches()
        return group_matches(matches, limit)

    async def get_standings(self) -> StandingsResponse:
        """Return the EFL Championship table."""
        if not self.mock_data_enabled:
            return StandingsResponse(competition=CHAMPIONSHIP, standings=[])

        return build_mock_standings()

    async def shutdown(self) -> None:
        """Close the provider's Redis connection."""
        await self.store.cache.close()

    async def _read_matches(self) -> list[Match]:
        """Read Wrexham's fixtures for both competitions and apply the live match data."""
        try:
            stored_fixtures = [
                await self.store.read_fixtures(competition.id)
                for competition in (CHAMPIONSHIP, FA_CUP)
            ]
            stored_live = await self.store.read_live_matches()
        except CacheAdapterError as ex:
            logger.error("Could not read Wrexham matches from Redis", extra={"error": str(ex)})
            self.metrics_client.increment("widgets.wrexham.redis.error", tags={"data": "matches"})
            raise WrexhamDataUnavailableError("Could not read Wrexham matches.") from ex

        if all(stored is None for stored in stored_fixtures):
            logger.warning("No Wrexham fixtures are stored in Redis")
            raise WrexhamDataUnavailableError("No Wrexham fixtures are stored.")

        matches_by_id: dict[int, Match] = {}
        for stored in stored_fixtures:
            if stored is not None:
                fixtures, _ = stored
                matches_by_id.update((match.id, match) for match in fixtures)

        if stored_live is not None:
            live_matches, _ = stored_live
            for match in live_matches:
                existing = matches_by_id.get(match.id)
                if existing is None or match.updated_at >= existing.updated_at:
                    matches_by_id[match.id] = match

        return list(matches_by_id.values())


def group_matches(matches: list[Match], limit: int) -> MatchesResponse:
    """Group matches by status.

    Previous matches are newest first; current and upcoming matches are earliest first.
    `limit` caps previous and upcoming matches.
    """
    by_kickoff = sorted(matches, key=lambda match: match.kickoff)

    previous = [match for match in reversed(by_kickoff) if match.status in PREVIOUS_STATUSES]
    current = [match for match in by_kickoff if match.status in CURRENT_STATUSES]
    upcoming = [match for match in by_kickoff if match.status in UPCOMING_STATUSES]

    return MatchesResponse(previous=previous[:limit], current=current, upcoming=upcoming[:limit])
