"""World Cup Soccer match provider."""

from datetime import UTC, date, datetime, time, timedelta
import logging
from typing import Protocol

from aiodogstatsd import Client
import sentry_sdk

from merino.exceptions import CacheAdapterError
from merino.governance.circuitbreakers import (
    WCSCircuitBreaker,
)
from merino.middleware.geolocation import Location
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event, Team
from merino.providers.wcs.fake_data import get_all_teams
from merino.providers.wcs.fake_live_data import build_live_events
from merino.providers.wcs.protocol import (
    EventInfo,
    LiveMatchesResponse,
    MatchesResponse,
    OtherRegionEntry,
    StreamEntry,
    TeamInfo,
    TeamsResponse,
    WatchLinks,
)
from merino.providers.wcs.utils import resolve_other_regions, resolve_watch_links
from merino.utils.metrics import get_metrics_client

_WINDOW = timedelta(days=21)
_LIVE_MATCH_LOOKBACK = timedelta(hours=6)
_LIVE_MATCH_LOOKAHEAD = timedelta(hours=2)
_CACHE_ERROR_METRIC = "wcs.cache_error"
logger = logging.getLogger(__name__)


class WcsSport(Protocol):
    """Cache-backed WCS sport behavior used by the widget provider."""

    async def get_events_by_date(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Return cached events within an optional inclusive datetime range."""
        ...

    async def get_all_teams(self) -> dict[int, Team]:
        """Return all cached teams."""
        ...

    async def get_eliminated_team_keys(self) -> set[str]:
        """Return cached eliminated team keys."""
        ...


class WcsProvider:
    """Serves match data for the World Cup Soccer endpoint."""

    def __init__(
        self,
        sport: WcsSport,
        metrics_client: Client | None = None,
        live_data_enabled: bool = False,
    ) -> None:
        """Create a WCS provider backed by the shared WCS sport cache."""
        self.sport = sport
        self.metrics_client = metrics_client or get_metrics_client()
        self.live_data_enabled = live_data_enabled

    @WCSCircuitBreaker(name="wcs_matches")
    async def get_matches(
        self,
        target_date: date,
        limit: int | None,
        team_keys: frozenset[str] | None,
    ) -> MatchesResponse:
        """Return matches in a +/- _WINDOW day window around `target_date`.

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
            raise

        for event in sorted(events, key=lambda e: e.date):
            event_info = EventInfo.from_event(event)
            event_date = _event_date(event)
            if _matches_team_filter(event_info, team_keys):
                if event_date < target_day:
                    previous.append(event_info)
                elif event_date == target_day:
                    current.append(event_info)
                else:
                    next_.append(event_info)

        if limit is not None:
            previous, current, next_ = previous[-limit:], current[:limit], next_[:limit]

        return MatchesResponse(previous=previous, current=current, next_=next_)

    @WCSCircuitBreaker(name="wcs_live_matches")
    async def get_live_matches(self, team_keys: frozenset[str] | None) -> LiveMatchesResponse:
        """Return live-endpoint events, sorted ascending by `date`.

        The Redis-backed path is gated so we can switch it on via config.
        `team_keys` restricts results to matches with that team on either side.
        """
        if not self.live_data_enabled:
            matches = [
                event
                for event in build_live_events(datetime.now(UTC).date())
                if _matches_team_filter(event, team_keys)
            ]
            return LiveMatchesResponse(matches=matches)

        now = datetime.now(UTC)
        window_start = now - _LIVE_MATCH_LOOKBACK
        window_end = now + _LIVE_MATCH_LOOKAHEAD
        try:
            events = await self.sport.get_events_by_date(start=window_start, end=window_end)
        except CacheAdapterError as ex:
            self._record_cache_error("live", ex)
            raise

        live_events: list[EventInfo] = []
        for event in sorted(events, key=lambda e: e.date):
            if not event.status.is_in_progress():
                continue
            event_info = EventInfo.from_event(event)
            if _matches_team_filter(event_info, team_keys):
                live_events.append(event_info)
        return LiveMatchesResponse(matches=live_events)

    @WCSCircuitBreaker(name="wcs_teams")
    async def get_teams(self) -> TeamsResponse:
        """Return cache-backed teams participating in the tournament."""
        try:
            teams = await self.sport.get_all_teams()
        except CacheAdapterError as ex:
            self._record_cache_error("teams", ex)
            raise

        cached_by_key = {team.key: team for team in teams.values()}
        if not cached_by_key:
            return TeamsResponse(teams=[])

        eliminated_keys = await self._get_eliminated_team_keys()
        response: list[TeamInfo] = []
        for roster_team in get_all_teams():
            cached_team = cached_by_key.get(roster_team.key)
            if cached_team is None:
                continue
            response.append(
                TeamInfo.from_team(
                    cached_team,
                    group=roster_team.group,
                    eliminated=cached_team.key in eliminated_keys,
                    region=cached_team.country or roster_team.region,
                )
            )
        # return teams sorted by name in A - Z order.
        return TeamsResponse(teams=sorted(response, key=lambda t: t.name))

    async def get_watch_links(
        self, geolocation: Location | None, accepted_languages: list[str]
    ) -> WatchLinks:
        """Return locale-resolved watch links for WCS matches."""
        # streams available in the user's own country and language
        your_region = [
            StreamEntry(product_name=link.product_name, entitlement=link.entitlement, url=link.url)
            for link in resolve_watch_links(geolocation, accepted_languages)
        ]

        # streams grouped by other countries, sorted by display code A-Z
        other_regions = []
        for display_code, links in resolve_other_regions(geolocation):
            streams = [
                StreamEntry(
                    product_name=link.product_name, entitlement=link.entitlement, url=link.url
                )
                for link in links
            ]
            other_regions.append(OtherRegionEntry(country_code=display_code, streams=streams))

        return WatchLinks(your_region=your_region, other_regions=other_regions)

    async def _get_eliminated_team_keys(self) -> set[str]:
        """Return team keys that no longer have a tournament path."""
        try:
            return await self.sport.get_eliminated_team_keys()
        except CacheAdapterError as ex:
            self._record_cache_error("teams", ex)
            return set()

    def _record_cache_error(self, endpoint: str, ex: CacheAdapterError) -> None:
        """Log and count cache read failures by endpoint."""
        logger.warning("WCS cache read failed while fetching %s: %s", endpoint, ex)
        self.metrics_client.increment(_CACHE_ERROR_METRIC, tags={"endpoint": endpoint})
        sentry_sdk.capture_exception(ex)


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
    return any(
        team is not None and team.key in team_keys for team in (event.home_team, event.away_team)
    )


def _matches_team_filter(event: EventInfo, team_keys: frozenset[str] | None) -> bool:
    """Return True when no filter is set or either side matches the requested teams."""
    return team_keys is None or _has_team(event, team_keys)
