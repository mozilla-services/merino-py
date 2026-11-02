"""Merino V1 API for New Tab widgets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from merino.providers.widgets import get_wrexham_provider
from merino.providers.widgets.wrexham.protocol import MatchesResponse, StandingsResponse
from merino.providers.widgets.wrexham.provider import WrexhamProvider

router = APIRouter()

DEFAULT_MATCH_LIMIT = 5
MAX_MATCH_LIMIT = 5  # will confirm max with product.


@router.get(
    "/widgets/wrexham/matches",
    tags=["widgets"],
    summary="Wrexham AFC matches",
    response_model=MatchesResponse,
)
async def get_wrexham_matches(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_MATCH_LIMIT,
            description="Maximum number of previous and upcoming matches to return.",
        ),
    ] = DEFAULT_MATCH_LIMIT,
    provider: WrexhamProvider = Depends(get_wrexham_provider),
) -> MatchesResponse:
    """Return Wrexham's EFL Championship and FA Cup matches, grouped into previous,
    current and upcoming.

    **Args**:
    - `limit`: [Optional] Maximum number of previous and upcoming matches. Defaults to 5.
    """
    return await provider.get_matches(limit)


@router.get(
    "/widgets/wrexham/standings",
    tags=["widgets"],
    summary="EFL Championship standings",
    response_model=StandingsResponse,
)
async def get_wrexham_standings(
    provider: WrexhamProvider = Depends(get_wrexham_provider),
) -> StandingsResponse:
    """Return the EFL Championship table, ordered by league position."""
    return await provider.get_standings()
