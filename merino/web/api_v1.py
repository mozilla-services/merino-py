"""Merino V1 API"""
import logging
from asyncio import Task
from collections import Counter
from functools import partial
from itertools import chain

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.requests import Request

from merino.config import settings
from merino.metrics import Client
from merino.middleware import ScopeKey
from merino.providers import get_providers
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.utils import task_runner
from merino.web.models_v1 import ProviderResponse, SuggestResponse

logger = logging.getLogger(__name__)
router = APIRouter()

SUGGEST_RESPONSE = {
    "suggestions": [],
    "client_variants": [],
    "server_variants": [],
    "request_id": "",
}

# Timeout for query tasks.
QUERY_TIMEOUT_SEC = settings.runtime.query_timeout_sec

# Client Variant Maximum - used to limit the number of
# possible client variants for experiments.
# See https://mozilla-services.github.io/merino/api.html#suggest
CLIENT_VARIANT_MAX = settings.runtime.client_variant_max


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
    """Query Merino for suggestions.

    Args:
    - `q`: The query string
    - `client_variants`: [Optional] A comma separated string indicating the client variants
    - `providers`: [Optional] A comma separated string indicating the suggestion providers for
      this query

    Returns:
    A list of suggestions or an empty list if nothing was found.
    """
    # Do you plan to release code behind a feature flag? Uncomment the following
    # line to get access to feature flags and then check if your feature flag is
    # enabled for this request by calling feature_flags.is_enabled("example").
    # feature_flags: FeatureFlags = request.scope[ScopeKey.FEATURE_FLAGS]

    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]

    active_providers, default_providers = sources
    if providers is not None:
        search_from = [
            active_providers[p]
            # Set used to filter out possible duplicate providers passed in.
            for p in set(providers.split(","))
            if p in active_providers
        ]
    else:
        search_from = default_providers

    srequest = SuggestionRequest(
        query=q, geolocation=request.scope[ScopeKey.GEOLOCATION]
    )

    lookups: list[Task] = []
    for p in search_from:
        task = metrics_client.timeit_task(
            p.query(srequest), f"providers.{p.name}.query"
        )
        # `timeit_task()` doesn't support task naming, need to set the task name manually
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
        chain.from_iterable(
            # TODO: handle exceptions. `task.result()` will throw if the task was
            # completed with an exception. This is OK for now as Merino will return
            # an HTTP 500 response for unhandled exceptions, but we will want better
            # exception handling for query tasks in the future.
            task.result()
            for task in completed_tasks
        )
    )

    emit_suggestions_per_metrics(metrics_client, suggestions, search_from)

    response = SuggestResponse(
        suggestions=suggestions,
        request_id=correlation_id.get(),
        # client_variant restriction: set to remove duplicates, [0:CLIENT_VARIANT_MAX] to
        # limit potential reflection back to client.
        client_variants=list(set(client_variants.split(",")))[:CLIENT_VARIANT_MAX]
        if client_variants
        else [],
    )
    return JSONResponse(content=jsonable_encoder(response))


def emit_suggestions_per_metrics(
    metrics_client: Client,
    suggestions: list[BaseSuggestion],
    searched_providers: list[BaseProvider],
) -> None:
    """Emit metrics for suggestions per request and suggestions per request by provider."""
    metrics_client.histogram("suggestions-per.request", value=len(suggestions))

    suggestion_counter = Counter(suggestion.provider for suggestion in suggestions)

    for provider in searched_providers:
        provider_name = provider.name
        suggestion_count = suggestion_counter[provider_name]
        metrics_client.histogram(
            f"suggestions-per.provider.{provider_name}",
            value=suggestion_count,
        )


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
    """Query Merino for suggestion providers.

    Returns:
    A list of search providers.
    """
    active_providers, _ = sources
    providers = [
        ProviderResponse(**{"id": id, "availability": provider.availability()})
        for id, provider in active_providers.items()
    ]
    return JSONResponse(content=jsonable_encoder(providers))
