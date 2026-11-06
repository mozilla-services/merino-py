"""Merino V1 API for New Tab widgets."""

from typing import Annotated

from aiodogstatsd import Client
from fastapi import APIRouter, Depends, Query, Response, Header, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.requests import Request

from merino.configs import settings
from merino.middleware import ScopeKey
from merino.providers.widgets import (
    get_iframed_widgets_provider,
    get_travel_provider,
    get_wrexham_provider,
)
from merino.providers.widgets.iframed.backends.protocol import IframedWidgetsResponse
from merino.providers.widgets.iframed.provider import Provider as IframedWidgetProvider
from merino.providers.widgets.wrexham.protocol import (
    ErrorResponse,
    MatchesResponse,
    StandingsResponse,
)
from merino.providers.widgets.wrexham.provider import (
    WrexhamDataUnavailableError,
    WrexhamProvider,
)

from merino.providers.widgets.travel.kayak.backends.protocol import TravelListing, TravelVertical
from merino.providers.widgets.travel.kayak.provider import Provider as TravelProvider

from merino.utils.query_processing.geo_params import (
    get_accepted_languages,
)

router = APIRouter()

HEADER_CHARACTER_MAX = settings.web.api.v1.header_character_max
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


@router.get(
    "/widgets/framed",
    tags=["widgets"],
    summary="All enabled widgets intended to be displayed in iframes",
    response_model=IframedWidgetsResponse,
)
async def get_iframed_widgets(
    request: Request,
    locale: Annotated[str, Query(max_length=16)] = "en-US",
    provider: IframedWidgetProvider = Depends(get_iframed_widgets_provider),
) -> Response:
    """Query merino for iframed widgets.

    **Args**:
    - locale: optionally provided by the caller, defaults to en-US (future-proofing design)
    - provider: Injected iframed widgets provider dependency used to build response.
    """
    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]

    with metrics_client.timeit("widgets.iframed.request.timing"):
        widgets_response = await provider.get_widgets(locale=locale)

    return JSONResponse(content=jsonable_encoder(widgets_response))


@router.get(
    "/widgets/travel",
    tags=["widgets"],
    summary="Travel listings",
    response_model=list[TravelListing],
)
async def get_travel_listings(
    request: Request,
    vertical: TravelVertical,
    q: Annotated[str, Query(min_length=3, max_length=64)],
    market: Annotated[str, Query(min_length=2, max_length=2, pattern="^[A-Za-z]{2}$")] = "US",
    accept_language: Annotated[str | None, Header(max_length=HEADER_CHARACTER_MAX)] = None,
    provider: TravelProvider = Depends(get_travel_provider),
) -> Response:
    """Query merino for travel listings.

    **Args**:
    - `vertical`: Travel vertical, one of `hotels`, `flights` or `cars`.
    - `q`: The search query, between 3 and 64 characters.
    - `market`: [Optional] Two-letter market (country) code, e.g. `US`, `GB`. Defaults to `US`.
    - provider: Injected travel provider dependency used to fetch listings.

    **Headers**:
    - `Accept-Language` - The primary language subtag of the highest `q` (quality) value
      locale in this header is used to localize listings. If the header is not included,
      empty or cannot be parsed, Merino will default to `en`.
    """
    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]
    languages = get_accepted_languages(accept_language)

    with metrics_client.timeit("travel.request.timing"):
        listings = await provider.get_listings(q, languages[0], market, vertical)

    return JSONResponse(content=jsonable_encoder(listings))
