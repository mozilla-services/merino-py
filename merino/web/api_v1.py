"""Merino V1 API"""
import logging
from asyncio import Task
from collections import Counter
from functools import partial
from itertools import chain

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Depends, Query
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

# Param to capture all enabled_by_default=True providers.
DEFAULT_PROVIDERS_PARAM_NAME: str = "default"

# Timeout for query tasks.
QUERY_TIMEOUT_SEC = settings.runtime.query_timeout_sec

# Client Variant Maximum - used to limit the number of
# possible client variants for experiments.
# See https://mozilla-services.github.io/merino/api.html#suggest
CLIENT_VARIANT_MAX = settings.web.api.v1.client_variant_max
QUERY_CHARACTER_MAX = settings.web.api.v1.query_character_max
CLIENT_VARIANT_CHARACTER_MAX = settings.web.api.v1.client_variant_character_max


@router.get(
    "/suggest",
    tags=["suggest"],
    summary="Merino suggest endpoint",
    response_model=SuggestResponse,
)
async def suggest(
    request: Request,
    q: str = Query(max_length=QUERY_CHARACTER_MAX),
    providers: str | None = None,
    client_variants: str
    | None = Query(default=None, max_length=CLIENT_VARIANT_CHARACTER_MAX),
    sources: tuple[dict[str, BaseProvider], list[BaseProvider]] = Depends(
        get_providers
    ),
) -> JSONResponse:
    """Query Merino for suggestions.

    This is the primary endpoint that consumes user input and suggests
    pages the user may want to visit. The expectation is that
    this is shown alongside other content the browser suggests
    to the user, such as bookmarks and history.

    This endpoint accepts GET requests and takes parameters as query string values
    and headers.

    **Args:**

    - `q`: The query that the user has typed. This is expected to be a partial
        input, sent as fast as once per keystroke, though a slower period may be
        appropriate for the user agent.
    - `client_variants`: [Optional] A comma-separated list of any experiments or
        rollouts that are affecting the client's Suggest experience. If Merino
        recognizes any of them it will modify its behavior accordingly.
    - `providers`: [Optional] A comma-separated list of providers to use for this
        request. See the `/providers` endpoint below for valid options. If provided,
        only suggestions from the listed providers will be returned. If not provided,
        Merino will use a built-in default set of providers. The default set of
        providers can be seen in the `/providers` endpoint. Supplying the `default`
        value to the `providers` parameter will return suggestions from the default providers.
        You can then pass other providers that are not enabled after `default`,
        allowing for customization of the suggestion request.

    **Headers:**

    - `Accept-Language` - The locale preferences expressed in this header in
      accordance with [RFC 2616 section 14.4][rfc-2616-14-4] will be used to
      determine suggestions. Merino maintains a list of supported locales. Merino
      will choose the locale from it's list that has the highest `q` (quality) value
      in the user's `Accept-Language` header. Locales with `q=0` will not be used.

      If no locales match, Merino will not return any suggestions. If the header is
      not included or empty, Merino will default to the `en-US` locale.

      If the highest quality, compatible language produces no suggestion results,
      Merino will return an empty list instead of attempting to query other
      languages.

    - `User-Agent` - A user's device form factor, operating system, and
      browser/Firefox version are detected from the `User-Agent` header included in
      the request.

    [rfc-2616-14-4]: https://datatracker.ietf.org/doc/html/rfc2616/#section-14.4

    **Other derived inputs:**

    - Location - The IP address of the user or nearest proxy will be used to
      determine location. This location may be as granular as city level, depending
      on server configuration.

      Users that use VPN services will be identified according to the VPN exit node
      they use, allowing them to change Merino's understanding of their location.
      VPN exit nodes are often mis-identified in geolocation databases, and may
      produce unreliable results.


    **Returns:**

    The response will be a JSON object containing the following keys:
    - `client_variants` - A list of strings specified from the `client_variants`
        parameter in the request.
    - `server_variants` - A list of strings indicating the server variants.
    - `request_id` - A string identifier identifying every API request sent from Firefox.
    - `suggestions` - A list of suggestions or an empty list if nothing was found.
        Please look at the documentation for `BaseSuggestion` model for information
        about what the model contains.

    **Response Headers:**

    Responses will carry standard HTTP caching headers that indicate the validity of
    the suggestions. User agents should prefer to provide the user with cached
    results as indicated by these headers.
    """
    # Do you plan to release code behind a feature flag? Uncomment the following
    # line to get access to feature flags and then check if your feature flag is
    # enabled for this request by calling feature_flags.is_enabled("example").
    # feature_flags: FeatureFlags = request.scope[ScopeKey.FEATURE_FLAGS]

    metrics_client: Client = request.scope[ScopeKey.METRICS_CLIENT]

    active_providers, default_providers = sources
    if providers is not None:
        # Set used to filter out possible duplicate providers passed in.
        provider_names: set[str] = set(providers.split(","))
        search_from: list[BaseProvider] = [
            active_providers[p] for p in provider_names if p in active_providers
        ]
        if DEFAULT_PROVIDERS_PARAM_NAME in provider_names:
            # Search the default providers if `default` wildcard parameter passed in `providers`.
            search_from.extend(p for p in default_providers if p not in search_from)
    else:
        search_from = default_providers

    lookups: list[Task] = []
    for p in search_from:
        srequest = SuggestionRequest(
            query=p.normalize_query(q), geolocation=request.scope[ScopeKey.GEOLOCATION]
        )
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
        # [:CLIENT_VARIANT_MAX] filter at end to drop any trailing string beyond max_split.
        client_variants=client_variants.split(",", maxsplit=CLIENT_VARIANT_MAX)[
            :CLIENT_VARIANT_MAX
        ]
        if client_variants
        else [],
    )
    return JSONResponse(content=jsonable_encoder(response, exclude_none=True))


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

    This endpoint gives a list of available providers, along with their
    _availability_. It accepts GET requests and takes no parameters.

    **Returns:**
    The response will be a JSON object containing the key `providers`, which is a
    map where the keys to this map are the IDs of the provider, and the values are
    provider metadata object. Each provider metadata object will have the following
    format:

    - `id` - A string that can be used to identify this provider. This ID can be
        used for the `providers` field of the suggest API.
    - `availability` - A string describing how this provider is used in Merino. It
        will be one of:
        - `"enabled_by_default"` - This provider will be used for requests that don't
            specify providers, and it should be provided to the user as a selection that
            can be turned off.
        - `"disabled_by_default"` - This provider is not used automatically. It should
            be provided to the user as a selection that could be turned on.
        - `"hidden"` - This provider is not used automatically. It should not be
            provided to the user as an option to turn on. It may be used for debugging
            or other internal uses.
    """
    active_providers, _ = sources
    providers = [
        ProviderResponse(**{"id": id, "availability": provider.availability()})
        for id, provider in active_providers.items()
    ]
    return JSONResponse(content=jsonable_encoder(providers))
