"""World Cup Soccer match provider."""

from datetime import date, datetime, timedelta

from merino.providers.wcs.fake_data import build_events
from merino.providers.wcs.protocol import EventInfo, MatchesResponse

_WINDOW = timedelta(days=7)


class WcsProvider:
    """Serves match data for the World Cup Soccer endpoint."""

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


def _event_date(event: EventInfo) -> date:
    """Return the UTC calendar date of `event`."""
    return datetime.fromisoformat(event.date).date()


def _has_team(event: EventInfo, team_keys: frozenset[str]) -> bool:
    """Return True if either side of `event` plays for one of `team_keys`."""
    return event.home_team.key in team_keys or event.away_team.key in team_keys
