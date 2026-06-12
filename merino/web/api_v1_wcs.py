"""Merino V1 World Cup Soccer API."""

from datetime import UTC, datetime
from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from merino.configs import settings
from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from circuitbreaker import CircuitBreakerError

from merino.providers.wcs import get_provider as get_wcs_provider
from merino.providers.wcs.protocol import (
    LiveMatchesResponse,
    MatchesResponse,
    TeamsResponse,
    WatchLinks,
)
from merino.providers.wcs.provider import WcsProvider
from merino.utils.query_processing.geo_params import (
    get_accepted_languages,
)

router = APIRouter()

HEADER_CHARACTER_MAX = settings.web.api.v1.header_character_max
WATCH_LINKS_CACHE_CONTROL_TTL = settings.providers.wcs.watch_links_cache_control_ttl
# All game/team data is refreshed on a 3 minute schedule; add a short cache
# to reduce some requests to the server while not compromising freshness
DEFAULT_CACHE_CONTROL_TTL = settings.providers.wcs.default_cache_control_ttl
_RETRY_AFTER = str(settings.providers.wcs.circuit_breaker_retry_after_sec)


@router.get(
    "/wcs/matches",
    tags=["wcs"],
    summary="World Cup Soccer matches near `date`, grouped by match state",
    response_model=MatchesResponse,
    response_model_by_alias=True,
)
async def get_wcs_matches(
    response: Response,
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

    The window is around `date`. `previous` holds completed or old matches,
    `current` holds active matches and scheduled matches during the short
    post-kickoff feed-lag grace period, and `next` holds upcoming matches.
    `previous` is newest-first; `current` and `next` are chronological.
    """
    target_date = date or datetime.now(UTC).date()
    team_keys = _parse_team_keys(teams)
    try:
        matches: MatchesResponse = await provider.get_matches(target_date, limit, team_keys)
        response.headers["Cache-Control"] = (
            f"public, s-maxage={DEFAULT_CACHE_CONTROL_TTL}, max-age={DEFAULT_CACHE_CONTROL_TTL}, stale-while-revalidate={DEFAULT_CACHE_CONTROL_TTL}"
        )
        return matches
    except CircuitBreakerError:
        raise HTTPException(
            status_code=503,
            detail="WCS temporarily unavailable",
            headers={"Retry-After": _RETRY_AFTER},
        )


@router.get(
    "/wcs/live",
    tags=["wcs"],
    summary="Currently live World Cup Soccer matches",
    response_model=LiveMatchesResponse,
)
async def get_wcs_live(
    response: Response,
    teams: Annotated[
        str | None,
        Query(description="Comma-separated 3-letter team keys, e.g. 'BRA,ARG'."),
    ] = None,
    provider: WcsProvider = Depends(get_wcs_provider),
) -> LiveMatchesResponse:
    """Return in-progress matches sorted ascending by date."""
    try:
        live_matches: LiveMatchesResponse = await provider.get_live_matches(
            _parse_team_keys(teams)
        )
        response.headers["Cache-Control"] = (
            f"public, s-maxage={DEFAULT_CACHE_CONTROL_TTL}, max-age={DEFAULT_CACHE_CONTROL_TTL}, stale-while-revalidate={DEFAULT_CACHE_CONTROL_TTL}"
        )
        return live_matches
    except CircuitBreakerError:
        raise HTTPException(
            status_code=503,
            detail="WCS temporarily unavailable",
            headers={"Retry-After": _RETRY_AFTER},
        )


@router.get(
    "/wcs/watch-links",
    tags=["wcs"],
    summary="Watch links for World Cup Soccer matches, resolved for the request locale",
    response_model=WatchLinks,
)
async def get_wcs_watch_links(
    request: Request,
    accept_language: Annotated[str | None, Header(max_length=HEADER_CHARACTER_MAX)] = None,
    provider: WcsProvider = Depends(get_wcs_provider),
) -> JSONResponse:
    """Return locale-resolved watch links for WCS matches."""
    geolocation: Location | None = request.scope.get(ScopeKey.GEOLOCATION)
    watch_links = await provider.get_watch_links(
        geolocation, get_accepted_languages(accept_language)
    )

    return JSONResponse(
        content=jsonable_encoder(watch_links),
        headers={"Cache-Control": f"private, max-age={WATCH_LINKS_CACHE_CONTROL_TTL}"},
    )


@router.get(
    "/wcs/teams",
    tags=["wcs"],
    summary="All World Cup Soccer teams",
    response_model=TeamsResponse,
)
async def get_wcs_teams(
    response: Response,
    provider: WcsProvider = Depends(get_wcs_provider),
) -> TeamsResponse:
    """Return all teams participating in the World Cup."""
    try:
        teams: TeamsResponse = await provider.get_teams()
        response.headers["Cache-Control"] = (
            f"public, s-maxage={DEFAULT_CACHE_CONTROL_TTL}, max-age={DEFAULT_CACHE_CONTROL_TTL}, stale-while-revalidate={DEFAULT_CACHE_CONTROL_TTL}"
        )
        return teams
    except CircuitBreakerError:
        raise HTTPException(
            status_code=503,
            detail="WCS temporarily unavailable",
            headers={"Retry-After": _RETRY_AFTER},
        )


def _parse_team_keys(teams: str | None) -> frozenset[str] | None:
    """Parse a comma-separated list of team keys into an upper-case frozen set."""
    if not teams:
        return None
    keys = frozenset(t.strip().upper() for t in teams.split(",") if t.strip())
    return keys or None
