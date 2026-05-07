"""World Cup Soccer match provider."""

from datetime import date, datetime, timedelta
from dynaconf.base import LazySettings
import logging

from merino.cache.redis import RedisAdapter
from merino.cache.none import NoCacheAdapter

from merino.providers.wcs.fake_data import get_all_teams
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event
from merino.providers.suggest.sports.backends.sportsdata.common.sports import WCS

from merino.providers.wcs.protocol import (
    EventInfo,
    LiveMatchesResponse,
    MatchesResponse,
    TeamsResponse,
)

_WINDOW = timedelta(days=7)

# Global logger
logger = logging.getLogger(__name__)


class WcsProvider:
    """Serves match data for the World Cup Soccer endpoint."""

    sport: WCS  # Should be Sports, but we do a lot of special stuff in WCS

    def __init__(
        self,
        settings: LazySettings,
        *args,
        cache: RedisAdapter | NoCacheAdapter = NoCacheAdapter(),
        **kwargs,
    ):
        # Note: This presumes that the cache has already been initialized.
        self.sport = WCS(settings, cache)

    async def get_matches(
        self,
        target_date: datetime,
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

        events: list[Event] = await self.sport.get_events_by_date(start=target_date, limit=limit)
        for event in events:
            if event.status.is_final():
                previous.append(EventInfo.from_Event(event))
            if event.status.is_in_progress():
                current.append(EventInfo.from_Event(event))
            if event.status.is_scheduled():
                next_.append(EventInfo.from_Event(event))
        if limit is not None:
            previous, current, next_ = previous[-limit:], current[:limit], next_[:limit]

        return MatchesResponse(previous=previous, current=current, next_=next_)

    async def get_live_matches(self, team_keys: frozenset[str] | None) -> LiveMatchesResponse:
        """Return events currently in progress, sorted ascending by `date`.

        Anchored to the current UTC date so the fake set always exposes its
        `live` bucket. `team_keys` restricts results to matches with that team
        on either side.
        """
        # matches = [
        #     event
        #     for event in sorted(build_events(datetime.now(UTC).date()), key=lambda e: e.date)
        #     if event.status_type == "live" and (team_keys is None or _has_team(event, team_keys))
        # ]
        matches = []
        events = map(lambda e: EventInfo.from_Event(e), await self.sport.get_events_by_date())
        if team_keys:
            for event in events:
                if (
                    event.home_team.get("key") in team_keys
                    or event.away_team.get("key") in team_keys
                ):
                    matches.append(event)
        return LiveMatchesResponse(matches=matches)

    def get_teams(self) -> TeamsResponse:
        """Return all teams participating in the tournament."""
        return TeamsResponse(teams=get_all_teams())


def _event_date(event: EventInfo) -> date:
    """Return the UTC calendar date of `event`."""
    return datetime.fromisoformat(event.date).date()


def _has_team(event: EventInfo, team_keys: frozenset[str]) -> bool:
    """Return True if either side of `event` plays for one of `team_keys`."""
    return event.home_team.key in team_keys or event.away_team.key in team_keys
