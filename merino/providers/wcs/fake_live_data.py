"""Static live match templates for the WCS live endpoint."""

from datetime import UTC, date, datetime, time

from pydantic import HttpUrl

from merino.providers.wcs.protocol import EventInfo, TeamInfo
from merino.providers.wcs.utils import get_team_colours
from merino.utils.logos import LogoCategory, load_manifest

_LOGO_HOST = "https://storage.googleapis.com/merino-images-prod"


def _icon(key: str) -> HttpUrl | None:
    """Return the nations flag URL for `key`, if it exists in the logo manifest."""
    entry = load_manifest().get(LogoCategory.Nations, key)
    return HttpUrl(f"{_LOGO_HOST}/{entry.url}") if entry else None


def _team(key: str, global_team_id: int, name: str) -> TeamInfo:
    return TeamInfo(
        key=key,
        global_team_id=global_team_id,
        name=name,
        region=key,
        colors=get_team_colours(key),
        icon_url=_icon(key),
        eliminated=False,
    )


_TEAMS: dict[str, TeamInfo] = {
    t.key: t
    for t in [
        _team("BRA", 90000001, "Brazil"),
        _team("GER", 90000003, "Germany"),
        _team("ENG", 90000005, "England"),
        _team("USA", 90000006, "United States"),
    ]
}


def build_live_events(anchor: date) -> list[EventInfo]:
    """Build fake live events anchored to `anchor`."""
    return [
        _event(
            anchor=anchor,
            hour=14,
            home_key="ENG",
            away_key="USA",
            home_score=1,
            away_score=0,
            period="2",
            clock="67",
            global_event_id=1002,
        ),
        _event(
            anchor=anchor,
            hour=17,
            home_key="BRA",
            away_key="GER",
            home_score=2,
            away_score=2,
            period="ET",
            clock="90+15",
            global_event_id=1003,
        ),
    ]


def _event(
    *,
    anchor: date,
    hour: int,
    home_key: str,
    away_key: str,
    home_score: int,
    away_score: int,
    period: str,
    clock: str,
    global_event_id: int,
) -> EventInfo:
    event_dt = datetime.combine(anchor, time(hour, tzinfo=UTC))
    return EventInfo(
        date=event_dt.isoformat(),
        global_event_id=global_event_id,
        home_team=_TEAMS[home_key],
        away_team=_TEAMS[away_key],
        period=period,
        home_score=home_score,
        away_score=away_score,
        home_extra=None,
        away_extra=None,
        home_penalty=None,
        away_penalty=None,
        clock=clock,
        updated=int(event_dt.timestamp()) - 3600,
        status="In Progress",
        status_type="live",
    )
