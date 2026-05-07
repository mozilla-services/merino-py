"""World Cup Soccer match provider."""

from datetime import date, datetime, timedelta, UTC
from dynaconf.base import LazySettings
import logging

from merino.cache.redis import RedisAdapter
from merino.cache.none import NoCacheAdapter


from merino.providers.suggest.sports.backends.sportsdata.common.data import Team
from merino.providers.suggest.sports.backends.sportsdata.common.sports import WCS
from merino.providers.wcs.protocol import TeamInfo
from merino.providers.wcs.fake_data import build_events

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

    def get_matches(
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

        # Sorting up-front means each bucket inherits ascending order without
        # a per-bucket sort pass.
        for event in sorted(build_events(target_date), key=lambda e: e.date):
            event_date = _event_date(event)
            if abs(event_date - target_date) > _WINDOW:
                continue
            if team_keys is not None and not _has_team(event, team_keys):
                continue
            if event_date < target_date:
                previous.append(event)
            elif event_date == target_date:
                current.append(event)
            else:
                next_.append(event)

        if limit is not None:
            previous, current, next_ = previous[-limit:], current[:limit], next_[:limit]

        return MatchesResponse(previous=previous, current=current, next_=next_)

    def get_live_matches(self, team_keys: frozenset[str] | None) -> LiveMatchesResponse:
        """Return events currently in progress, sorted ascending by `date`.

        Anchored to the current UTC date so the fake set always exposes its
        `live` bucket. `team_keys` restricts results to matches with that team
        on either side.
        """
        matches = [
            event
            for event in sorted(build_events(datetime.now(UTC).date()), key=lambda e: e.date)
            if event.status_type == "live" and (team_keys is None or _has_team(event, team_keys))
        ]
        return LiveMatchesResponse(matches=matches)

    async def get_teams(self) -> TeamsResponse:
        """Return all teams participating in the tournament."""
        all_teams: dict[int, Team] = await self.sport.get_all_teams()
        if not all_teams:
            logger.warning("No team info found for WCS")
            return TeamsResponse(teams=[])
        teams: list[TeamInfo] = list(
            map(lambda team: TeamInfo.from_Team(team), list(all_teams.values()))
        )
        return TeamsResponse(teams=list(teams))


def _event_date(event: EventInfo) -> date:
    """Return the UTC calendar date of `event`."""
    return datetime.fromisoformat(event.date).date()


def _has_team(event: EventInfo, team_keys: frozenset[str]) -> bool:
    """Return True if either side of `event` plays for one of `team_keys`."""
    return event.home_team.key in team_keys or event.away_team.key in team_keys
