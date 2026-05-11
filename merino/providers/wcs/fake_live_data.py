"""Static match templates for the WCS live endpoint."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from merino.providers.wcs.fake_data import get_all_teams
from merino.providers.wcs.protocol import EventInfo, TeamInfo

type StatusType = Literal[
    "past",
    "live",
    "scheduled",
    "interrupted",
    "postponed",
    "canceled",
    "awarded",
]


@dataclass(frozen=True, slots=True)
class EventTemplate:
    """Template row for a fake WCS live-endpoint event."""

    day_offset: int
    hour: int
    home_key: str
    away_key: str
    status_type: StatusType
    status: str
    home_score: int | None = None
    away_score: int | None = None
    home_extra: int | None = None
    away_extra: int | None = None
    home_penalty: int | None = None
    away_penalty: int | None = None
    period: str | None = None
    clock: str | None = None


_TEMPLATES: list[EventTemplate] = [
    # Existing finals / scheduled / live
    EventTemplate(
        day_offset=-1,
        hour=14,
        home_key="BRA",
        away_key="ARG",
        status_type="past",
        status="Final",
        home_score=2,
        away_score=1,
        period="FT",
        clock="90",
    ),
    EventTemplate(
        day_offset=-1,
        hour=18,
        home_key="GER",
        away_key="FRA",
        status_type="past",
        status="Final",
        home_score=1,
        away_score=1,
        home_extra=1,
        away_extra=1,
        home_penalty=5,
        away_penalty=4,
        period="FT(P)",
        clock="120",
    ),
    EventTemplate(
        day_offset=0,
        hour=14,
        home_key="ENG",
        away_key="USA",
        status_type="live",
        status="In Progress",
        home_score=1,
        away_score=0,
        period="2",
        clock="67",
    ),
    EventTemplate(
        day_offset=0,
        hour=17,
        home_key="BRA",
        away_key="GER",
        status_type="live",
        status="In Progress",
        home_score=2,
        away_score=2,
        period="ET",
        clock="90+15",
    ),
    EventTemplate(
        day_offset=1,
        hour=15,
        home_key="ARG",
        away_key="ENG",
        status_type="scheduled",
        status="Scheduled",
        period="1",
        clock="0",
    ),
    EventTemplate(
        day_offset=1,
        hour=19,
        home_key="FRA",
        away_key="USA",
        status_type="scheduled",
        status="Scheduled",
        period="1",
        clock="0",
    ),
    # First half live - scoreless
    EventTemplate(
        day_offset=0,
        hour=10,
        home_key="BRA",
        away_key="USA",
        status_type="live",
        status="In Progress",
        home_score=0,
        away_score=0,
        period="1",
        clock="12",
    ),
    # First half live - away team leading
    EventTemplate(
        day_offset=0,
        hour=11,
        home_key="ARG",
        away_key="FRA",
        status_type="live",
        status="In Progress",
        home_score=0,
        away_score=1,
        period="1",
        clock="38",
    ),
    # Halftime / break
    EventTemplate(
        day_offset=0,
        hour=12,
        home_key="GER",
        away_key="ENG",
        status_type="live",
        status="Break",
        home_score=1,
        away_score=1,
        period="HT",
        clock="45",
    ),
    # Second half stoppage time
    EventTemplate(
        day_offset=0,
        hour=13,
        home_key="USA",
        away_key="BRA",
        status_type="live",
        status="In Progress",
        home_score=2,
        away_score=2,
        period="2",
        clock="90+3",
    ),
    # Extra time first half
    EventTemplate(
        day_offset=0,
        hour=15,
        home_key="FRA",
        away_key="GER",
        status_type="live",
        status="In Progress",
        home_score=1,
        away_score=1,
        home_extra=0,
        away_extra=0,
        period="ET1",
        clock="98",
    ),
    # Extra time halftime
    EventTemplate(
        day_offset=0,
        hour=16,
        home_key="ENG",
        away_key="ARG",
        status_type="live",
        status="Break",
        home_score=1,
        away_score=1,
        home_extra=0,
        away_extra=0,
        period="ETHT",
        clock="105",
    ),
    # Extra time second half
    EventTemplate(
        day_offset=0,
        hour=17,
        home_key="BRA",
        away_key="FRA",
        status_type="live",
        status="In Progress",
        home_score=1,
        away_score=1,
        home_extra=1,
        away_extra=0,
        period="ET2",
        clock="117",
    ),
    # Penalty shootout live
    EventTemplate(
        day_offset=0,
        hour=18,
        home_key="GER",
        away_key="USA",
        status_type="live",
        status="In Progress",
        home_score=2,
        away_score=2,
        home_extra=0,
        away_extra=0,
        home_penalty=2,
        away_penalty=1,
        period="P",
        clock="120",
    ),
    # Final after extra time
    EventTemplate(
        day_offset=-1,
        hour=20,
        home_key="ARG",
        away_key="BRA",
        status_type="past",
        status="Final",
        home_score=1,
        away_score=1,
        home_extra=0,
        away_extra=1,
        period="AET",
        clock="120",
    ),
    # Final after penalties (alternate outcome)
    EventTemplate(
        day_offset=-1,
        hour=21,
        home_key="FRA",
        away_key="ENG",
        status_type="past",
        status="Final",
        home_score=0,
        away_score=0,
        home_extra=0,
        away_extra=0,
        home_penalty=3,
        away_penalty=4,
        period="FT(P)",
        clock="120",
    ),
    # Suspended live match
    EventTemplate(
        day_offset=0,
        hour=22,
        home_key="USA",
        away_key="ARG",
        status_type="interrupted",
        status="Suspended",
        home_score=1,
        away_score=0,
        period="2",
        clock="63",
    ),
    # Postponed match
    EventTemplate(
        day_offset=1,
        hour=12,
        home_key="ENG",
        away_key="GER",
        status_type="postponed",
        status="Postponed",
    ),
    # Canceled match
    EventTemplate(
        day_offset=1,
        hour=13,
        home_key="FRA",
        away_key="BRA",
        status_type="canceled",
        status="Canceled",
    ),
    # Awarded / forfeit match
    EventTemplate(
        day_offset=-1,
        hour=13,
        home_key="USA",
        away_key="ENG",
        status_type="awarded",
        status="Awarded",
        home_score=3,
        away_score=0,
        period="FT",
        clock="90",
    ),
]

_TEAM_KEYS = {template.home_key for template in _TEMPLATES} | {
    template.away_key for template in _TEMPLATES
}
# TeamInfo objects come from fake_data.py, including the pinned flag icon URLs used by /wcs/teams.
_TEAMS: dict[str, TeamInfo] = {
    team.key: team for team in get_all_teams() if team.key in _TEAM_KEYS
}


def build_live_events(anchor: date) -> list[EventInfo]:
    """Build fake live-endpoint events anchored to `anchor`."""
    events = [
        _event(
            anchor=anchor,
            template=template,
            global_event_id=global_event_id,
        )
        for global_event_id, template in enumerate(_TEMPLATES, start=1001)
    ]
    return sorted(events, key=lambda event: event.date)


def _event(
    *,
    anchor: date,
    template: EventTemplate,
    global_event_id: int,
) -> EventInfo:
    event_dt = datetime.combine(
        anchor + timedelta(days=template.day_offset),
        time(template.hour, tzinfo=UTC),
    )
    return EventInfo(
        date=event_dt.isoformat(),
        global_event_id=global_event_id,
        home_team=_team(template.home_key),
        away_team=_team(template.away_key),
        period=template.period or "",
        home_score=template.home_score,
        away_score=template.away_score,
        home_extra=template.home_extra,
        away_extra=template.away_extra,
        home_penalty=template.home_penalty,
        away_penalty=template.away_penalty,
        clock=template.clock or "",
        updated=int(event_dt.timestamp()) - 3600,
        status=template.status,
        status_type=template.status_type,
    )


def _team(key: str) -> TeamInfo:
    """Return WCS team metadata for `key`."""
    try:
        return _TEAMS[key]
    except KeyError as ex:
        raise ValueError(f"Missing WCS team data for {key}") from ex
