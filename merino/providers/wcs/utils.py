"""Utility helpers for the WCS provider."""

import json
from pathlib import Path
from typing import cast

TEAM_COLOURS: dict[str, list[str]] = cast(
    dict[str, list[str]],
    json.loads(
        (Path(__file__).parent.parent.parent / "data" / "wcs_team_colours.json").read_text()
    ),
)


def get_team_colours(team_key: str) -> list[str]:
    """Return the hex colour list for a team, or an empty list if not available."""
    return TEAM_COLOURS.get(team_key, [])
