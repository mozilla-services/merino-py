"""World Cup Soccer match provider."""

from datetime import UTC, date, datetime, time, timedelta
import logging
from typing import Protocol

from aiodogstatsd import Client

from merino.exceptions import CacheAdapterError
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event
from merino.providers.suggest.sports.backends.sportsdata.common.sports import WCS
from merino.providers.wcs.protocol import TeamInfo
from merino.providers.wcs.fake_data import get_all_teams
from merino.providers.wcs.fake_live_data import build_live_events
from merino.providers.wcs.protocol import (
    EventInfo,
    LiveMatchesResponse,
    MatchesResponse,
    TeamsResponse,
)
from merino.utils.metrics import get_metrics_client

_WINDOW = timedelta(days=7)
_CACHE_ERROR_METRIC = "wcs.cache_error"
logger = logging.getLogger(__name__)


class WcsSport(Protocol):
    """Cache-backed WCS sport behavior used by the widget provider."""

    async def get_events_by_date(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Return cached events within an optional inclusive datetime range."""
        ...


class WcsProvider:
    """Serves match data for the World Cup Soccer endpoint."""

    def __init__(self, sport: WCS, metrics_client: Client | None = None) -> None:
        """Create a WCS provider backed by the shared WCS sport cache."""
        self.sport = sport
        self.metrics_client = metrics_client or get_metrics_client()

    async def get_matches(
        self,
        target_date: date,
        limit: int | None,
        team_keys: frozenset[str] | None,
    ) -> MatchesResponse:
        """Return matches in the +/- 7 day window around `target_date`.

        Events are bucketed into `previous`, `current`, and `next` relative to
        `target_date` and sorted ascending by event date. `limit` keeps the
        entries closest to `target_date` in each bucket; `team_keys` restricts
        results to matches involving any of the listed teams.
        """
        previous: list[EventInfo] = []
        current: list[EventInfo] = []
        next_: list[EventInfo] = []

        target_day = _target_day(target_date)
        window_start = datetime.combine(target_day - _WINDOW, time.min, tzinfo=UTC)
        window_end = datetime.combine(target_day + _WINDOW, time.max, tzinfo=UTC)
        try:
            events = await self.sport.get_events_by_date(start=window_start, end=window_end)
        except CacheAdapterError as ex:
            self._record_cache_error("matches", ex)
            return MatchesResponse(previous=[], current=[], next_=[])

        for event in sorted(events, key=lambda e: e.date):
            event_info = EventInfo.from_event(event)
            event_date = _event_date(event)
            if team_keys is not None and not _has_team(event_info, team_keys):
                continue
            if event_date < target_day:
                previous.append(event_info)
            elif event_date == target_day:
                current.append(event_info)
            else:
                next_.append(event_info)

        if limit is not None:
            previous, current, next_ = previous[-limit:], current[:limit], next_[:limit]

        return MatchesResponse(previous=previous, current=current, next_=next_)

    async def get_live_matches(self, team_keys: frozenset[str] | None) -> LiveMatchesResponse:
        """Return fake live-endpoint events, sorted ascending by `date`.

        `team_keys` restricts results to matches with that team on either side.
        """
        matches = [
            event
            for event in sorted(build_live_events(datetime.now(UTC).date()), key=lambda e: e.date)
            if team_keys is None or _has_team(event, team_keys)
        ]
        return LiveMatchesResponse(matches=matches)

    async def get_teams(self) -> TeamsResponse:
        """Return all teams participating in the tournament."""
        response = []
        teams = await self.sport.get_all_teams()
        for team in teams.values():
            response.append(TeamInfo.from_team(team))
        return TeamsResponse(teams=response)

    def _record_cache_error(self, endpoint: str, ex: CacheAdapterError) -> None:
        """Log and count cache read failures by endpoint."""
        logger.warning("WCS cache read failed while fetching %s: %s", endpoint, ex)
        self.metrics_client.increment(_CACHE_ERROR_METRIC, tags={"endpoint": endpoint})


def _target_day(target_date: date) -> date:
    """Return the UTC calendar day for a date or datetime request value."""
    if isinstance(target_date, datetime):
        return target_date.astimezone(UTC).date()
    return target_date


def _event_date(event: Event) -> date:
    """Return the UTC calendar date of `event`."""
    event_datetime = event.date
    if event_datetime.tzinfo is None:
        event_datetime = event_datetime.replace(tzinfo=UTC)
    return event_datetime.astimezone(UTC).date()


def _has_team(event: EventInfo, team_keys: frozenset[str]) -> bool:
    """Return True if either side of `event` plays for one of `team_keys`."""
    return event.home_team.key in team_keys or event.away_team.key in team_keys
