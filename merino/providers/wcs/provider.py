"""World Cup Soccer match provider."""

from datetime import date, datetime, timedelta

from merino.providers.wcs.backends.protocol import WcsBackend
from merino.providers.wcs.protocol import EventInfo, LiveMatchesResponse, MatchesResponse

_WINDOW = timedelta(days=7)


class WcsProvider:
    """Serves match data for the World Cup Soccer endpoint."""

    def __init__(self, backend: WcsBackend) -> None:
        """Initialise with a backend supplying both schedule and live events."""
        self._backend = backend

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
        for event in sorted(self._backend.get_events(), key=lambda e: e.date):
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

        return MatchesResponse(previous=previous, current=current, next=next_)

    def get_live_matches(self, team_keys: frozenset[str] | None) -> LiveMatchesResponse:
        """Return events currently in progress, sorted ascending by `date`.

        `team_keys` restricts results to matches with that team on either side.
        """
        matches = [
            event
            for event in sorted(self._backend.get_live_events(), key=lambda e: e.date)
            if event.status_type == "live" and (team_keys is None or _has_team(event, team_keys))
        ]
        return LiveMatchesResponse(matches=matches)


def _event_date(event: EventInfo) -> date:
    """Return the UTC calendar date of `event`."""
    return datetime.fromisoformat(event.date).date()


def _has_team(event: EventInfo, team_keys: frozenset[str]) -> bool:
    """Return True if either side of `event` plays for one of `team_keys`."""
    return event.home_team.key in team_keys or event.away_team.key in team_keys
