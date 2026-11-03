"""Merino V1 API for New Tab widgets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from merino.configs import settings
from merino.providers.widgets import get_wrexham_provider
from merino.providers.widgets.wrexham.protocol import MatchesResponse, StandingsResponse
from merino.providers.widgets.wrexham.provider import (
    WrexhamDataUnavailableError,
    WrexhamProvider,
)

router = APIRouter()

DEFAULT_MATCH_LIMIT = 5
MAX_MATCH_LIMIT = 5  # will confirm max with product.

_matches_cache_control_ttl = settings.widgets.providers.wrexham.matches_cache_control_ttl_sec


def _wrexham_unavailable() -> JSONResponse:
    """Return the error response for Wrexham data that can't be served."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "statusCode": status.HTTP_503_SERVICE_UNAVAILABLE,
            "message": "Wrexham data is temporarily unavailable. Please try again later.",
        },
    )


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
        content=jsonable_encoder(matches),
        headers={
            "Cache-Control": (
                f"public, max-age={_matches_cache_control_ttl}, "
                f"s-maxage={_matches_cache_control_ttl}"
            )
        },
    )


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
