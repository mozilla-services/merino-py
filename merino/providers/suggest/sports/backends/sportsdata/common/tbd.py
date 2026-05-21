"""Predicate for the TBD placeholder team used in cached WCS events."""

from typing import Any

from merino.providers.suggest.sports.backends.sportsdata.common.wcs_elimination import (
    TBD_TEAM_KEY,
)


def is_tbd_event_team(team: dict[str, Any]) -> bool:
    """Return True for the compact placeholder team used in cached WCS events."""
    try:
        team_id = int(team.get("id", -1))
    except TypeError, ValueError:
        team_id = -1
    return str(team.get("key", "")).upper() == TBD_TEAM_KEY and team_id == 0
