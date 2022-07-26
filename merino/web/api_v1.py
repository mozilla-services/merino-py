import asyncio
from itertools import chain

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from merino.providers import get_providers
from merino.providers.base import BaseProvider
from merino.web.models_v1 import (
    NonsponsoredSuggestion,
    ProviderResponse,
    SponsoredSuggestion,
    SuggestResponse,
)

router = APIRouter()


SUGGEST_RESPONSE = {
    "suggestions": [],
    "client_variants": [],
    "server_variants": [],
    "request_id": "",
}


@router.get("/suggest", tags=["suggest"], summary="Merino suggest endpoint")
async def suggest(
    q: str,
    providers: str | None = None,
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(
        get_providers
    ),
    summary="Merino suggest endpoint",
    response_model=SuggestResponse,
) -> JSONResponse:
    """
    Query Merino for suggestions.

    Args:
    - `q`: The query string
    - `providers`: [Optional] A comma separated string indicating the suggestion providers for
      this query

    Returns:
    A list of suggestions or an empty list if nothing was found.
    """
    active_providers, default_providers = sources
    if providers is not None:
        search_from = [
            active_providers[p] for p in providers.split(",") if p in active_providers
        ]
    else:
        search_from = default_providers
    lookups = [p.query(q) for p in search_from]
    results = await asyncio.gather(*lookups)

    suggestions = [
        SponsoredSuggestion(**suggestion)
        if suggestion["is_sponsored"]
        else NonsponsoredSuggestion(**suggestion)
        for suggestion in chain(*results)
    ]
    response = SuggestResponse(suggestions=suggestions)
    return JSONResponse(content=jsonable_encoder(response))


@router.get(
    "/providers",
    tags=["providers"],
    summary="Merino provider endpoint",
    response_model=list[ProviderResponse],
)
async def providers(
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(
        get_providers
    ),
) -> JSONResponse:
    """
    Query Merino for suggestion providers.

    Returns:
    A list of search providers.
    """
    active_providers, _ = sources
    providers = [
        ProviderResponse(**{"id": id, "availability": provider.availability()})
        for id, provider in active_providers.items()
    ]
    return JSONResponse(content=jsonable_encoder(providers))
