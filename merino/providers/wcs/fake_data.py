"""Static team data for the WCS teams endpoint."""

import json
from pathlib import Path
from typing import Any

from pydantic import HttpUrl

from merino.providers.wcs.protocol import TeamInfo
from merino.providers.wcs.utils import get_team_colours
from merino.utils.logos import LogoCategory, load_manifest

# Stage does not always provide a CDN host override for the nations logo bucket.
# Pin WCS flag URLs to the production image bucket so stage and prod render the
# same assets.
_LOGO_HOST = "https://storage.googleapis.com/merino-images-prod"


def _icon(key: str) -> HttpUrl | None:
    """Return the nations flag URL for `key`, if it exists in the logo manifest."""
    entry = load_manifest().get(LogoCategory.Nations, key)
    return HttpUrl(f"{_LOGO_HOST}/{entry.url}") if entry else None


def _team_from_json(entry: dict[str, Any]) -> TeamInfo:
    """Build a TeamInfo from a wcs_teams.json entry."""
    key = str(entry["Key"])
    return TeamInfo(
        key=key,
        global_team_id=int(entry["GlobalTeamId"]),
        name=str(entry["Name"]),
        region=key,
        colors=get_team_colours(key),
        icon_url=_icon(key),
        eliminated=entry.get("eliminated", False),
    )


def _load_all_teams() -> list[TeamInfo]:
    """Load all teams from the static wcs_teams.json file."""
    path = Path(__file__).parent.parent.parent / "data" / "wcs_teams.json"
    with path.open() as f:
        return [_team_from_json(entry) for entry in json.load(f)]


_ALL_TEAMS: list[TeamInfo] = _load_all_teams()


def get_all_teams() -> list[TeamInfo]:
    """Return all tournament teams from the static teams list."""
    return _ALL_TEAMS
