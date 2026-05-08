"""Utility helpers for the WCS provider."""

from merino.providers.wcs.team_colors import TEAM_COLOURS


def get_team_colours(team_key: str) -> list[str]:
    """Return the hex colour list for a team, or an empty list if not available."""
    return TEAM_COLOURS.get(team_key, [])
