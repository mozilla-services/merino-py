"""Provider for the Wrexham widget endpoints."""

import logging
from datetime import UTC, datetime, timedelta

from circuitbreaker import CircuitBreakerError

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham import metrics
from merino.providers.widgets.wrexham.circuitbreaker import WrexhamCircuitBreaker, guarded_by
from merino.providers.widgets.wrexham.protocol import (
    CHAMPIONSHIP,
    FA_CUP,
    Competition,
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

FINISHED_MATCH_GRACE_PERIOD = timedelta(
    seconds=settings.widgets.providers.wrexham.finished_match_grace_period_sec
)
# SportsDataIO keeps updating matches for hours after they finish (3.8 hours or more after
# kickoff in past data), so a recent update only means a match just finished if it kicked off
# within this time. It's longer than the longest match (about 2h45 with extra time and
# penalties), with room for a late kickoff.
MAX_MATCH_LENGTH = timedelta(hours=3, minutes=30)

circuit_breaker = WrexhamCircuitBreaker(name="wrexham")
metrics.observe_circuit_breaker(circuit_breaker)

# The competitions whose fixtures the matches endpoint serves, in the order they're read.
FIXTURE_COMPETITIONS = (CHAMPIONSHIP, FA_CUP)

StoredMatches = tuple[list[Match], datetime]


class WrexhamDataUnavailableError(Exception):
    """Raised when Wrexham data can't be served."""


class WrexhamProvider:
    """Serves Wrexham matches and EFL Championship standings to the widget."""

    store: WrexhamStore

    def __init__(self, store: WrexhamStore) -> None:
        self.store = store

    async def get_matches(self, limit: int) -> MatchesResponse:
        """Return previous, current and upcoming matches.

        `limit` caps the number of previous and upcoming matches.

        Raises:
            - `WrexhamDataUnavailableError` if the matches can't be read from Redis.
        """
        now = datetime.now(UTC)
        matches = await self._read_matches(now)
        return group_matches(matches, limit, now=now)

    async def get_standings(self) -> StandingsResponse:
        """Return the EFL Championship table, ordered by league position.

        The table is empty when none is available yet, e.g. before the season starts.

        Raises:
            - `WrexhamDataUnavailableError` if the standings can't be read from Redis.
        """
        try:
            stored = await self._read_stored_standings()
        except CircuitBreakerError as ex:
            raise WrexhamDataUnavailableError("Wrexham circuit breaker is open.") from ex
        except CacheAdapterError as ex:
            _record_redis_error("standings", ex)
            raise WrexhamDataUnavailableError("Could not read Wrexham standings.") from ex

        if stored is None:
            logger.warning("No Wrexham standings are stored in Redis")
            raise WrexhamDataUnavailableError("No Wrexham standings are stored.")

        standings, fetched_at = stored
        _record_data_age("standings", "standings", fetched_at, datetime.now(UTC))
        return StandingsResponse(
            competition=CHAMPIONSHIP,
            standings=sorted(standings, key=lambda standing: standing.position),
        )

    async def shutdown(self) -> None:
        """Close the provider's Redis connection."""
        await self.store.cache.close()

    @guarded_by(circuit_breaker)
    async def _read_stored_matches(
        self,
    ) -> tuple[list[StoredMatches | None], StoredMatches | None]:
        """Read both competitions' fixtures and the live match data from Redis.

        Redis errors are raised, so the circuit breaker can count them.
        """
        fixtures = [
            await self.store.read_fixtures(competition.id) for competition in FIXTURE_COMPETITIONS
        ]
        return fixtures, await self.store.read_live_matches()

    @guarded_by(circuit_breaker)
    async def _read_stored_standings(self) -> tuple[list[Standing], datetime] | None:
        """Read the Championship table from Redis.

        Redis errors are raised, so the circuit breaker can count them.
        """
        return await self.store.read_standings()

    async def _read_matches(self, now: datetime) -> list[Match]:
        """Read Wrexham's fixtures for both competitions and apply the live match data."""
        try:
            stored_fixtures, stored_live = await self._read_stored_matches()
        except CircuitBreakerError as ex:
            raise WrexhamDataUnavailableError("Wrexham circuit breaker is open.") from ex
        except CacheAdapterError as ex:
            _record_redis_error("matches", ex)
            raise WrexhamDataUnavailableError("Could not read Wrexham matches.") from ex

        if all(stored is None for stored in stored_fixtures):
            logger.warning("No Wrexham fixtures are stored in Redis")
            raise WrexhamDataUnavailableError("No Wrexham fixtures are stored.")

        matches_by_id: dict[int, Match] = {}
        for competition, stored in zip(FIXTURE_COMPETITIONS, stored_fixtures, strict=True):
            if stored is not None:
                fixtures, fetched_at = stored
                _record_data_age("matches", "fixtures", fetched_at, now, competition)
                matches_by_id.update((match.id, match) for match in fixtures)

        if stored_live is not None:
            live_matches, fetched_at = stored_live
            _record_data_age("matches", "live_matches", fetched_at, now)
            for match in live_matches:
                existing = matches_by_id.get(match.id)
                if existing is None or match.updated_at >= existing.updated_at:
                    matches_by_id[match.id] = match

        return list(matches_by_id.values())


def _record_redis_error(endpoint: str, ex: CacheAdapterError) -> None:
    """Log and count a failed Redis read for `endpoint` ("matches" or "standings")."""
    logger.error(f"Could not read Wrexham {endpoint} from Redis", extra={"error": str(ex)})
    metrics.api_redis_error_count.add(1, {"endpoint": endpoint})


def _record_data_age(
    endpoint: str,
    data_type: str,
    fetched_at: datetime,
    now: datetime,
    competition: Competition | None = None,
) -> None:
    """Record the age of the `data_type` data served by `endpoint` as a histogram, tagged by
    `competition` for data that belongs to one competition (fixtures).
    """
    age = (now - fetched_at).total_seconds()
    attributes = {"endpoint": endpoint, "data_type": data_type}
    if competition is not None:
        attributes["competition"] = competition.name
    metrics.api_data_age.record(age, attributes)


def just_finished(match: Match, now: datetime) -> bool:
    """Return whether `match` finished within the grace period, so it stays in `current`."""
    return (
        match.status == MatchStatus.Final
        and now - match.updated_at <= FINISHED_MATCH_GRACE_PERIOD
        and timedelta(0) <= now - match.kickoff <= MAX_MATCH_LENGTH
    )


def group_matches(matches: list[Match], limit: int, now: datetime) -> MatchesResponse:
    """Group matches by status.

    Previous matches are newest first; current and upcoming matches are earliest first.
    `limit` caps previous and upcoming matches. A match that just finished stays in `current`
    for a short grace period.
    """
    by_kickoff = sorted(matches, key=lambda match: match.kickoff)

    previous = [
        match
        for match in reversed(by_kickoff)
        if match.status in PREVIOUS_STATUSES and not just_finished(match, now)
    ]
    current = [
        match
        for match in by_kickoff
        if match.status in CURRENT_STATUSES or just_finished(match, now)
    ]
    upcoming = [match for match in by_kickoff if match.status in UPCOMING_STATUSES]

    return MatchesResponse(previous=previous[:limit], current=current, upcoming=upcoming[:limit])
