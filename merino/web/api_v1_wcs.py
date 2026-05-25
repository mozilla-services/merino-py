"""Merino V1 World Cup Soccer API."""

from datetime import UTC, datetime
from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from merino.providers.wcs import get_provider as get_wcs_provider
from merino.providers.wcs.protocol import LiveMatchesResponse, MatchesResponse, TeamsResponse
from merino.providers.wcs.provider import WcsProvider

router = APIRouter()


@router.get(
    "/wcs/matches",
    tags=["wcs"],
    summary="World Cup Soccer matches in the +/- 7 day window around `date`",
    response_model=MatchesResponse,
    response_model_by_alias=True,
)
async def get_wcs_matches(
    date: Annotated[
        Date | None, Query(description="RFC date YYYY-MM-DD; defaults to today UTC.")
    ] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    teams: Annotated[
        str | None,
        Query(description="Comma-separated 3-letter team keys, e.g. 'BRA,ARG'."),
    ] = None,
    provider: WcsProvider = Depends(get_wcs_provider),
) -> MatchesResponse:
    """Return matches grouped into `previous`, `current`, and `next`.

    The window is `+/- 7 days` around `date`. `current` holds matches on `date`,
    `previous` is older, `next` is newer. Each bucket is sorted ascending by
    event date.
    """
    target_date = date or datetime.now(UTC).date()
    team_keys = _parse_team_keys(teams)
    matches: MatchesResponse = await provider.get_matches(target_date, limit, team_keys)
    return matches


@router.get(
    "/wcs/live",
    tags=["wcs"],
    summary="Currently live World Cup Soccer matches",
    response_model=LiveMatchesResponse,
)
async def get_wcs_live(
    teams: Annotated[
        str | None,
        Query(description="Comma-separated 3-letter team keys, e.g. 'BRA,ARG'."),
    ] = None,
    provider: WcsProvider = Depends(get_wcs_provider),
) -> LiveMatchesResponse:
    """Return in-progress matches sorted ascending by date."""
    live_matches: LiveMatchesResponse = await provider.get_live_matches(_parse_team_keys(teams))
    return live_matches


@router.get(
    "/wcs/teams",
    tags=["wcs"],
    summary="All World Cup Soccer teams",
    response_model=TeamsResponse,
)
async def get_wcs_teams(
    provider: WcsProvider = Depends(get_wcs_provider),
) -> TeamsResponse:
    """Return all teams participating in the World Cup."""
    teams: TeamsResponse = await provider.get_teams()
    return teams


def _parse_team_keys(teams: str | None) -> frozenset[str] | None:
    """Parse a comma-separated list of team keys into an upper-case frozen set."""
    if not teams:
        return None
    keys = frozenset(t.strip().upper() for t in teams.split(",") if t.strip())
    return keys or None
