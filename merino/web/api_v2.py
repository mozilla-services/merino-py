"""Merino V2 API - OHTTP Compatible Endpoints"""

import logging
from asyncio import Task
from functools import partial
from itertools import chain
from typing import Annotated

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse
from starlette.requests import Request
from aiodogstatsd import Client
from starlette.responses import Response

from merino.configs import settings
from merino.curated_recommendations import (
    get_provider as get_corpus_api_provider,
)
from merino.curated_recommendations.provider import (
    CuratedRecommendationsProvider,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsRequest,
    CuratedRecommendationsResponse,
)
from merino.middleware import ScopeKey
from merino.middleware.user_agent import UserAgent
from merino.providers.suggest import get_providers as get_suggest_providers
from merino.providers.suggest.base import BaseProvider, SuggestionRequest
from merino.providers.suggest.weather.provider import NO_LOCATION_KEY_SUGGESTION
from merino.utils import task_runner

from merino.utils.api.cache_control import get_ttl_for_cache_control_header_for_suggestions
from merino.utils.api.metrics import emit_suggestions_per_metrics

from merino.web.models_v1 import ProviderResponse, SuggestResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Param to capture all enabled_by_default=True providers.
DEFAULT_PROVIDERS_PARAM_NAME: str = "default"

# Timeout for query tasks.
QUERY_TIMEOUT_SEC = settings.runtime.query_timeout_sec

# Client Variant Maximum - used to limit the number of
# possible client variants for experiments.
CLIENT_VARIANT_MAX = settings.web.api.v1.client_variant_max
QUERY_CHARACTER_MAX = settings.web.api.v1.query_character_max
CLIENT_VARIANT_CHARACTER_MAX = settings.web.api.v1.client_variant_character_max
HEADER_CHARACTER_MAX = settings.web.api.v1.header_character_max


@router.get(
    "/suggest",
    tags=["suggest-v2"],
    summary="Merino suggest endpoint v2 (OHTTP compatible)",
    response_model=SuggestResponse,
)
async def suggest_v2(
    request: Request,
    q: Annotated[str, Query(max_length=QUERY_CHARACTER_MAX)],
    # V2: Require explicit geolocation instead of IP-based detection
    country: Annotated[str, Query(max_length=2, min_length=2)],
    region: Annotated[str, Query(max_length=QUERY_CHARACTER_MAX)],
    city: Annotated[str, Query(max_length=QUERY_CHARACTER_MAX)],
    # V2: Require explicit locale instead of Accept-Language header
    locale: Annotated[str, Query(max_length=10)] = "en-US",
    # V2: Require explicit form factor instead of User-Agent detection
    form_factor: Annotated[str, Query(pattern="^(phone|tablet|desktop)$")] = "desktop",
    providers: str | None = None,
    client_variants: str | None = Query(default=None, max_length=CLIENT_VARIANT_CHARACTER_MAX),
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(get_suggest_providers),
    request_type: Annotated[str | None, Query(pattern="^(location|weather)$")] = None,
) -> Response:
    """Query Merino for suggestions (V2 - OHTTP Compatible).

    This is the V2 endpoint designed for OHTTP compatibility. Unlike V1, this endpoint
    requires explicit location and device information instead of deriving them from
    request headers and IP addresses, which are not available in OHTTP requests.

    **Key differences from V1:**
    - Requires explicit `country`, `region`, `city` parameters (no IP-based geolocation)
    - Requires explicit `locale` parameter (no Accept-Language header parsing)
    - Requires explicit `form_factor` parameter (no User-Agent parsing)

    **Args:**
    - `q`: The query that the user has typed
    - `country`: ISO 3166-2 country code (required). E.g.: "US"
    - `region`: Region/subdivision code (required). E.g.: "CA" for California
    - `city`: City name (required). E.g.: "San Francisco"
    - `locale`: Locale preference (required). E.g.: "en-US", "de-DE"
    - `form_factor`: Device form factor (required). One of: "phone", "tablet", "desktop"
    - `providers`: Optional comma-separated list of providers
    - `client_variants`: Optional experiment/rollout identifiers
    - `request_type`: Optional request type for weather provider ("location" or "weather")

    **Returns:**
    Same response format as V1 suggest endpoint.
    """
    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]

    # Create a synthetic UserAgent for V2 requests
    user_agent = UserAgent(
        form_factor=form_factor,
        os_family="Unknown",  # Not available in OHTTP
        browser="Unknown",  # Not available in OHTTP
    )

    active_providers, default_providers = sources
    if providers is not None:
        provider_names: set[str] = set(providers.split(","))
        search_from: list[BaseProvider] = [
            active_providers[p] for p in provider_names if p in active_providers
        ]
        if DEFAULT_PROVIDERS_PARAM_NAME in provider_names:
            search_from.extend(p for p in default_providers if p not in search_from)
    else:
        search_from = default_providers

    lookups: list[Task] = []
    languages = [locale]  # Use explicit locale instead of parsing Accept-Language

    # Create explicit geolocation from provided parameters
    geolocation = {"country": country, "region": region, "city": city}

    for p in search_from:
        srequest = SuggestionRequest(
            query=p.normalize_query(q),
            geolocation=geolocation,
            request_type=request_type,
            languages=languages,
            user_agent=user_agent,
        )
        p.validate(srequest)
        task = metrics_client.timeit_task(p.query(srequest), f"providers.{p.name}.query")
        task.set_name(p.name)
        lookups.append(task)

    completed_tasks, _ = await task_runner.gather(
        lookups,
        timeout=max(
            (provider.query_timeout_sec for provider in search_from),
            default=QUERY_TIMEOUT_SEC,
        ),
        timeout_cb=partial(task_runner.metrics_timeout_handler, metrics_client),
    )

    suggestions = list(
        chain.from_iterable(task.result() for task in completed_tasks if task.exception() is None)
    )

    if len(suggestions) == 1 and suggestions[0] is NO_LOCATION_KEY_SUGGESTION:
        return Response(status_code=204)

    emit_suggestions_per_metrics(metrics_client, suggestions, search_from)

    response = SuggestResponse(
        suggestions=suggestions,
        request_id=correlation_id.get(),
        client_variants=(
            client_variants.split(",", maxsplit=CLIENT_VARIANT_MAX)[:CLIENT_VARIANT_MAX]
            if client_variants
            else []
        ),
    )

    # response headers
    response_headers = {}
    ttl = get_ttl_for_cache_control_header_for_suggestions(search_from, suggestions)
    response_headers["Cache-control"] = f"private, max-age={ttl}"

    return ORJSONResponse(
        content=jsonable_encoder(response, exclude_none=True),
        headers=response_headers,
    )


@router.post(
    "/curated-recommendations",
    summary="Curated recommendations for New Tab (V2 - OHTTP Compatible)",
)
async def curated_content_v2(
    curated_recommendations_request: CuratedRecommendationsRequest,
    provider: CuratedRecommendationsProvider = Depends(get_corpus_api_provider),
) -> CuratedRecommendationsResponse:
    """Query Merino for curated recommendations (V2 - OHTTP Compatible).

    This endpoint is identical to the V1 curated-recommendations endpoint but
    is exposed under the V2 API for OHTTP compatibility. The request body
    should include all necessary location and locale information explicitly.

    **JSON body:**
    - `locale`: The Firefox installed locale (required)
    - `region`: The country-level region (recommended for OHTTP requests)
    - `count`: Maximum number of recommendations to return
    - `topics`: Preferred topics list
    - `feeds`: Sections list
    - `inferredInterests`: Topics with relative interest values
    - `experimentName`: Nimbus experiment name
    - `experimentBranch`: Experiment branch name
    """
    return await provider.fetch(curated_recommendations_request)


@router.get(
    "/providers",
    tags=["providers-v2"],
    summary="Merino provider endpoint (V2)",
    response_model=list[ProviderResponse],
)
async def providers_v2(
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(get_suggest_providers),
) -> ORJSONResponse:
    """Query Merino for suggestion providers (V2).

    Identical to V1 providers endpoint but under V2 API namespace.
    """
    active_providers, _ = sources
    providers = [
        ProviderResponse(**{"id": id, "availability": provider.availability()})
        for id, provider in active_providers.items()
    ]
    return ORJSONResponse(content=jsonable_encoder(providers))
