"""Merino V1 API for New Tab widgets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from merino.configs import settings
from merino.providers.widgets import get_wrexham_provider
from merino.providers.widgets.wrexham.protocol import (
    ErrorResponse,
    MatchesResponse,
    StandingsResponse,
)
from merino.providers.widgets.wrexham.provider import (
    WrexhamDataUnavailableError,
    WrexhamProvider,
)

router = APIRouter()

DEFAULT_MATCH_LIMIT = 5
MAX_MATCH_LIMIT = 5

_matches_cache_control_ttl = settings.widgets.providers.wrexham.matches_cache_control_ttl_sec
_standings_cache_control_ttl = settings.widgets.providers.wrexham.standings_cache_control_ttl_sec

_WREXHAM_UNAVAILABLE_MESSAGE = "Wrexham data is temporarily unavailable. Please try again later."


def _cache_control(ttl: int) -> dict[str, str]:
    """Return a Cache-Control header letting Fastly and browsers cache a response for `ttl`
    seconds.
    """
    return {"Cache-Control": f"public, max-age={ttl}, s-maxage={ttl}"}


def _wrexham_unavailable() -> JSONResponse:
    """Return the error response for Wrexham data that can't be served."""
    error = ErrorResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, message=_WREXHAM_UNAVAILABLE_MESSAGE
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error.model_dump(by_alias=True),
    )


@router.get(
    "/widgets/wrexham/matches",
    tags=["widgets"],
    summary="Wrexham AFC matches",
    response_model=MatchesResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Wrexham data can't be read right now.",
        }
    },
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
) -> Response:
    """Return Wrexham's EFL Championship and FA Cup matches, grouped into previous,
    current and upcoming.

    **Args**:
    - `limit`: [Optional] Maximum number of previous and upcoming matches. Defaults to 5.
    """
    try:
        matches = await provider.get_matches(limit)
    except WrexhamDataUnavailableError:
        return _wrexham_unavailable()

    return JSONResponse(
        content=jsonable_encoder(matches), headers=_cache_control(_matches_cache_control_ttl)
    )


@router.get(
    "/widgets/wrexham/standings",
    tags=["widgets"],
    summary="EFL Championship standings",
    response_model=StandingsResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Wrexham data can't be read right now.",
        }
    },
)
async def get_wrexham_standings(
    provider: WrexhamProvider = Depends(get_wrexham_provider),
) -> Response:
    """Return the EFL Championship table, ordered by league position. The table is empty when
    none is available yet, e.g. before the season starts.
    """
    try:
        standings = await provider.get_standings()
    except WrexhamDataUnavailableError:
        return _wrexham_unavailable()

    return JSONResponse(
        content=jsonable_encoder(standings), headers=_cache_control(_standings_cache_control_ttl)
    )
