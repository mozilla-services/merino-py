"""Static teams and match templates for the WCS match endpoint.

Match dates are generated relative to the requested anchor date so every
response contains two completed (yesterday), two in-progress (today), and
two upcoming (tomorrow) events.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from pydantic import HttpUrl

from merino.providers.wcs.protocol import EventInfo, TeamInfo
from merino.providers.wcs.utils import get_team_colours
from merino.utils.logos import LogoCategory, load_manifest

# Stage's `image_gcs_v2.cdn_hostname` is unset, so `get_logo_url` produces
# `https://logos/...`. Pin to the prod bucket directly so stage renders the
# same flags as production. Remove once SRE wires up the stage CDN host.
_LOGO_HOST = "https://storage.googleapis.com/merino-images-prod"


def _icon(key: str) -> HttpUrl | None:
    entry = load_manifest().get(LogoCategory.Nations, key)
    return HttpUrl(f"{_LOGO_HOST}/{entry.url}") if entry else None


def _team(
    key: str,
    global_team_id: int,
    name: str,
    region: str,
    colors: list[str],
    group: str,
) -> TeamInfo:
    return TeamInfo(
        key=key,
        global_team_id=global_team_id,
        name=name,
        region=region,
        colors=colors,
        icon_url=_icon(key),
        eliminated=False,
    )


# Real WCS team_IDs are 90000000-offset; named colors mirror the upstream feed.
_TEAMS: dict[str, TeamInfo] = {
    t.key: t
    for t in [
        _team("BRA", 90000001, "Brazil", "BRA", ["Yellow", "Green", "Blue"], "Group A"),
        _team("ARG", 90000002, "Argentina", "ARG", ["Sky Blue", "White"], "Group A"),
        _team("GER", 90000003, "Germany", "GER", ["Black", "Red", "Yellow"], "Group B"),
        _team("FRA", 90000004, "France", "FRA", ["Blue", "White", "Red"], "Group B"),
        _team("ENG", 90000005, "England", "ENG", ["White", "Red"], "Group C"),
        _team("USA", 90000006, "United States", "USA", ["Navy", "White", "Red"], "Group C"),
    ]
}


# NOTE: This is building and providing static team data only to allow for UI devlepment.
# Actual data from external APIs will be wired in follow up work.
def _team_from_json(entry: dict) -> TeamInfo:
    """Build a TeamInfo from a wcs_teams.json entry."""
    key = entry["Key"]
    return TeamInfo(
        key=key,
        global_team_id=entry["GlobalTeamId"],
        name=entry["Name"],
        region=key,
        colors=get_team_colours(key),
        icon_url=_icon(key),
        eliminated=False,
    )


def _load_all_teams() -> list[TeamInfo]:
    """Load all teams from wcs_teams.json file."""
    path = Path(__file__).parent.parent.parent / "data" / "wcs_teams.json"
    with path.open() as f:
        return [_team_from_json(entry) for entry in json.load(f)]


_ALL_TEAMS: list[TeamInfo] = _load_all_teams()


def get_all_teams() -> list[TeamInfo]:
    """Return all tournament teams from the static teams list."""
    return _ALL_TEAMS


# (day_offset, hour_utc, home, away, status_type, home_score, away_score,
#  home_extra, away_extra, home_penalty, away_penalty, period, clock, status)
#
# Yesterday's GER vs FRA went to extra time and penalties — the only fixture
# that exercises the extra/penalty fields. The live BRA vs GER is in extra
# time so its `clock` shows the "90+x" format.
_TEMPLATES: list[tuple] = [
    (-1, 14, "BRA", "ARG", "past", 2, 1, None, None, None, None, "FT", "90", "Final"),
    (-1, 18, "GER", "FRA", "past", 1, 1, 1, 1, 5, 4, "FT(P)", "120", "Final"),
    (0, 14, "ENG", "USA", "live", 1, 0, None, None, None, None, "2", "67", "In Progress"),
    (0, 17, "BRA", "GER", "live", 2, 2, None, None, None, None, "ET", "90+15", "In Progress"),
    (1, 15, "ARG", "ENG", "scheduled", None, None, None, None, None, None, "1", "0", "Scheduled"),
    (1, 19, "FRA", "USA", "scheduled", None, None, None, None, None, None, "1", "0", "Scheduled"),
]


def build_events(anchor: date) -> list[EventInfo]:
    """Build the full set of fake events anchored to `anchor` (UTC).

    Output is byte-stable for a given anchor: identifiers and timestamps are
    derived from the anchor and the template index, with no clock reads.
    """
    events: list[EventInfo] = []
    for index, (
        day_offset,
        hour,
        home_key,
        away_key,
        status_type,
        home_score,
        away_score,
        home_extra,
        away_extra,
        home_penalty,
        away_penalty,
        period,
        clock,
        status,
    ) in enumerate(_TEMPLATES):
        event_dt = datetime.combine(anchor + timedelta(days=day_offset), time(hour, tzinfo=UTC))
        events.append(
            EventInfo(
                date=event_dt.isoformat(),
                global_event_id=1000 + index,
                home_team=_TEAMS[home_key],
                away_team=_TEAMS[away_key],
                period=period,
                home_score=home_score,
                away_score=away_score,
                home_extra=home_extra,
                away_extra=away_extra,
                home_penalty=home_penalty,
                away_penalty=away_penalty,
                clock=clock,
                updated=int(event_dt.timestamp()) - 3600,
                status=status,
                status_type=status_type,
            )
        )
    return events
