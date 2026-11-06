"""Provider for the Wrexham widget endpoints."""

import logging
from datetime import UTC, datetime

import aiodogstatsd
from circuitbreaker import CircuitBreakerError

from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham.circuitbreaker import WrexhamCircuitBreaker, guarded_by
from merino.providers.widgets.wrexham.mock_data import build_mock_matches, build_mock_standings
from merino.providers.widgets.wrexham.protocol import (
    CHAMPIONSHIP,
    FA_CUP,
    Match,
    MatchesResponse,
    MatchStatus,
    Standing,
    StandingsResponse,
)
from merino.providers.widgets.wrexham.store import WrexhamStore

logger = logging.getLogger(__name__)

PREVIOUS_STATUSES = frozenset({MatchStatus.Final, MatchStatus.Canceled})
CURRENT_STATUSES = frozenset(
    {MatchStatus.InProgress, MatchStatus.Break, MatchStatus.Delayed, MatchStatus.Suspended}
)
UPCOMING_STATUSES = frozenset({MatchStatus.Scheduled, MatchStatus.Postponed})

# One breaker per endpoint, so Redis problems reading one kind of data don't block the other.
matches_circuit_breaker = WrexhamCircuitBreaker(name="wrexham_matches")
standings_circuit_breaker = WrexhamCircuitBreaker(name="wrexham_standings")

StoredMatches = tuple[list[Match], datetime]


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
        """Return the EFL Championship table, ordered by league position.

        The table is empty when none is available yet, e.g. before the season starts.

        Raises:
            - `WrexhamDataUnavailableError` if the standings can't be read from Redis.
        """
        if self.mock_data_enabled:
            return build_mock_standings()

        try:
            stored = await self._read_stored_standings()
        except CircuitBreakerError as ex:
            raise WrexhamDataUnavailableError("Wrexham standings circuit breaker is open.") from ex
        except CacheAdapterError as ex:
            self._record_redis_error("standings", ex)
            raise WrexhamDataUnavailableError("Could not read Wrexham standings.") from ex

        if stored is None:
            logger.warning("No Wrexham standings are stored in Redis")
            raise WrexhamDataUnavailableError("No Wrexham standings are stored.")

        standings, _ = stored
        return StandingsResponse(
            competition=CHAMPIONSHIP,
            standings=sorted(standings, key=lambda standing: standing.position),
        )

    async def shutdown(self) -> None:
        """Close the provider's Redis connection."""
        await self.store.cache.close()

    @guarded_by(matches_circuit_breaker)
    async def _read_stored_matches(
        self,
    ) -> tuple[list[StoredMatches | None], StoredMatches | None]:
        """Read both competitions' fixtures and the live match data from Redis.

        Redis errors are raised, so the circuit breaker can count them.
        """
        fixtures = [
            await self.store.read_fixtures(competition.id)
            for competition in (CHAMPIONSHIP, FA_CUP)
        ]
        return fixtures, await self.store.read_live_matches()

    @guarded_by(standings_circuit_breaker)
    async def _read_stored_standings(self) -> tuple[list[Standing], datetime] | None:
        """Read the Championship table from Redis.

        Redis errors are raised, so the circuit breaker can count them.
        """
        return await self.store.read_standings()

    def _record_redis_error(self, data: str, ex: CacheAdapterError) -> None:
        """Log and count a failed Redis read of `data` (e.g. "matches")."""
        logger.error(f"Could not read Wrexham {data} from Redis", extra={"error": str(ex)})
        self.metrics_client.increment("widgets.wrexham.redis.error", tags={"data": data})

    async def _read_matches(self) -> list[Match]:
        """Read Wrexham's fixtures for both competitions and apply the live match data."""
        try:
            stored_fixtures, stored_live = await self._read_stored_matches()
        except CircuitBreakerError as ex:
            raise WrexhamDataUnavailableError("Wrexham matches circuit breaker is open.") from ex
        except CacheAdapterError as ex:
            self._record_redis_error("matches", ex)
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
