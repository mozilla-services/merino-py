"""Schedule loader for WCS endpoints from the bundled wcs_schedules.json."""

from datetime import UTC, datetime
from functools import cache

import orjson
from importlib.resources import files
from pydantic import HttpUrl

from merino.providers.wcs.protocol import EventInfo, TeamInfo
from merino.utils.logos import LogoCategory, load_manifest

# Stage's `image_gcs_v2.cdn_hostname` is unset, so `get_logo_url` produces
# `https://logos/...`. Pin to the prod bucket directly so stage renders the
# same flags as production. Remove once SRE wires up the stage CDN host.
_LOGO_HOST = "https://storage.googleapis.com/merino-images-prod"


@cache
def _load_teams() -> dict[str, dict]:
    """Return wcs_teams.json keyed by team Key."""
    data = (files("merino.data") / "wcs_teams.json").read_bytes()
    return {t["Key"]: t for t in orjson.loads(data)}


def get_icon(key: str) -> HttpUrl | None:
    """Return the flag URL for `key` from the logos manifest, or None."""
    entry = load_manifest().get(LogoCategory.Nations, key)
    return HttpUrl(f"{_LOGO_HOST}/{entry.url}") if entry else None


def _make_team(key: str, global_id: int, name: str, group: str) -> TeamInfo:
    """Build a TeamInfo from the schedule feed, hydrating colors from wcs_teams.json."""
    team = _load_teams().get(key, {})
    colors = [
        c
        for c in (team.get("ClubColor1"), team.get("ClubColor2"), team.get("ClubColor3"))
        if c
    ]
    return TeamInfo(
        key=key,
        global_team_id=global_id,
        name=name,
        region=key,
        colors=colors,
        icon_url=get_icon(key),
        group=group,
        eliminated=False,
        standing={"wins": 0, "losses": 0, "draws": 0, "points": 0},
    )


def _status_type(status: str) -> str:
    """Map a feed Status string to the simplified status_type token."""
    if status == "Scheduled":
        return "scheduled"
    if status.startswith("F"):
        return "past"
    return "live"


def _map_period(status: str, period_raw: str) -> str:
    """Derive a period descriptor from the feed Status and Period fields."""
    if status == "Scheduled":
        return "1"
    if status.startswith("F"):
        if period_raw == "Overtime":
            return "FT(ET)"
        if period_raw in ("Shootout", "Penalty"):
            return "FT(P)"
        return "FT"
    if period_raw in ("Overtime", "ExtraTime"):
        return "ET"
    return "1"


@cache
def build_events() -> list[EventInfo]:
    """Load all match events from the bundled wcs_schedules.json."""
    data = (files("merino.data") / "wcs_schedules.json").read_bytes()
    rounds = orjson.loads(data)
    events: list[EventInfo] = []
    for round_data in rounds:
        for game in round_data.get("Games", []):
            # Skip TBD knockout slots where teams aren't determined yet.
            if game.get("HomeTeamKey") is None or game.get("AwayTeamKey") is None:
                continue
            status = game.get("Status", "Scheduled")
            period_raw = game.get("Period") or "Regular"
            clock = game.get("ClockDisplay") or "0"

            updated_str = game.get("UpdatedUtc") or game.get("Updated", "")
            updated_ts = 0
            if updated_str:
                try:
                    dt = datetime.fromisoformat(updated_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    updated_ts = int(dt.timestamp())
                except ValueError:
                    pass

            events.append(
                EventInfo(
                    # DateTime in the feed is naive UTC; append offset so
                    # datetime.fromisoformat() is unambiguous downstream.
                    date=game["DateTime"] + "+00:00",
                    global_event_id=game["GlobalGameId"],
                    home_team=_make_team(
                        game["HomeTeamKey"],
                        game["GlobalHomeTeamId"],
                        game["HomeTeamName"],
                        game.get("Group", ""),
                    ),
                    away_team=_make_team(
                        game["AwayTeamKey"],
                        game["GlobalAwayTeamId"],
                        game["AwayTeamName"],
                        game.get("Group", ""),
                    ),
                    period=_map_period(status, period_raw),
                    home_score=game.get("HomeTeamScore"),
                    away_score=game.get("AwayTeamScore"),
                    home_extra=game.get("HomeTeamScoreExtraTime"),
                    away_extra=game.get("AwayTeamScoreExtraTime"),
                    home_penalty=game.get("HomeTeamScorePenalty"),
                    away_penalty=game.get("AwayTeamScorePenalty"),
                    clock=clock,
                    updated=updated_ts,
                    status=status,
                    status_type=_status_type(status),
                )
            )
    return events
