"""Merino V1 API"""
import asyncio
import os
from itertools import chain

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.requests import Request

from merino.featureflags import FeatureFlags
from merino.metrics import Client
from merino.middleware import ScopeKey
from merino.providers import get_providers
from merino.providers.base import BaseProvider, SuggestionRequest
from merino.web.models_v1 import ProviderResponse, SuggestResponse

router = APIRouter()

SUGGEST_RESPONSE = {
    "suggestions": [],
    "client_variants": [],
    "server_variants": [],
    "request_id": "",
}


@router.get(
    "/suggest",
    tags=["suggest"],
    summary="Merino suggest endpoint",
    response_model=SuggestResponse,
)
async def suggest(
    request: Request,
    q: str,
    providers: str | None = None,
    client_variants: str | None = None,
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(
        get_providers
    ),
) -> JSONResponse:
    """
    Query Merino for suggestions.

    Args:
    - `q`: The query string
    - `client_variants`: [Optional] A comma separated string indicating the client variants
    - `providers`: [Optional] A comma separated string indicating the suggestion providers for
      this query

    Returns:
    A list of suggestions or an empty list if nothing was found.
    """
    feature_flags: FeatureFlags = request.scope[ScopeKey.FEATURE_FLAGS]
    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]

    if os.environ["MERINO_ENV"] == "testing":
        if feature_flags.is_enabled("test-perc-enabled"):
            print("test-perc-enabled is enabled")

        if feature_flags.is_enabled("test-perc-enabled"):
            # TODO: Do we expect a decision for a `random` scheme flag to be
            # consistent across the handling of a request? Do we expect to call
            # is_enabled() multiple times for a feature flag or just once have
            # retrieve the recorded decision for future calls in
            # @record_decision?
            print("test-perc-enabled is enabled")

        if feature_flags.is_enabled("test-perc-enabled-session"):
            print("test-perc-enabled-session is enabled")

    active_providers, default_providers = sources
    if providers is not None:
        search_from = [
            active_providers[p] for p in providers.split(",") if p in active_providers
        ]
    else:
        search_from = default_providers

    srequest = SuggestionRequest(
        query=q, geolocation=request.scope[ScopeKey.GEOLOCATION]
    )

    # # Retrieve feature flags decisions as metric tags
    # metrics_tags = feature_flags_as_tags(request.scope[ScopeKey.FEATURE_FLAGS])

    lookups = [
        metrics_client.timeit_task(
            p.query(srequest),
            f"providers.{p.name}.query",
        )
        for p in search_from
    ]

    suggestions_lists = await asyncio.gather(*lookups)
    suggestions = [s for s in chain(*suggestions_lists)]

    response = SuggestResponse(
        suggestions=suggestions,
        request_id=correlation_id.get(),
        client_variants=client_variants.split(",") if client_variants else [],
    )
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
