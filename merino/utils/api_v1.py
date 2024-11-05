"""A utility module for Merino v1 API."""

from collections import Counter
import functools
from typing import Optional

from aiodogstatsd import Client
from fastapi import HTTPException, Request

from merino.config import settings

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.providers.base import BaseProvider, BaseSuggestion
from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.weather.provider import Provider as WeatherProvider
from merino.providers.weather.provider import Suggestion as WeatherSuggestion

# Default Cache-Control TTL value for /suggest endpoint responses
DEFAULT_CACHE_CONTROL_TTL: int = settings.runtime.default_suggestions_response_ttl_sec


@functools.lru_cache(maxsize=1000)
def get_accepted_languages(languages: str | None) -> list[str]:
    """Retrieve filtered list of languages that merino accepts."""
    if languages:
        try:
            if languages == "*":
                return ["en-US"]
            result = []
            for lang in languages.split(","):
                parts = lang.strip().split(";q=")
                language = parts[0]
                quality = float(parts[1]) if len(parts) > 1 else 1.0  # Default q-value is 1.0
                result.append((language, quality))

            # Sort by quality in descending order
            result.sort(key=lambda x: x[1], reverse=True)
            return [language[0] for language in result]
        except Exception:
            return ["en-US"]
    return ["en-US"]


def validate_suggest_custom_location_params(
    city: Optional[str], region: Optional[str], country: Optional[str]
):
    """Validate that city, region & country params are either all present or all omitted."""
    if any([country, region, city]) and not all([country, region, city]):
        raise HTTPException(
            status_code=400,
            detail="Invalid query parameters: `city`, `region`, and `country` are either all present or all omitted.",
        )


def refine_geolocation_for_suggestion(
    request: Request, city: Optional[str], region: Optional[str], country: Optional[str]
) -> Location:
    """Generate a refined geolocation object based on optional city, region, and country parameters
    for the suggest endpoint. If all parameters are provided, the geolocation data is updated
    with the specified city, region, and country. Otherwise, the original geolocation data is used.

    Args:
        request (Request): The request containing geolocation data in the scope.
        city (Optional[str]): The name of the city to include in the geolocation, if available.
        region (Optional[str]): The name of the region to include in the geolocation, if available.
        country (Optional[str]): The name of the country to include in the geolocation, if available.

    Returns:
        Location: A Location object with refined geolocation data based on provided parameters.
    """
    geolocation: Location = request.scope[ScopeKey.GEOLOCATION].model_copy()
    if country and region and city:
        geolocation = request.scope[ScopeKey.GEOLOCATION].model_copy(
            update={"city": city, "regions": [region], "country": country}
        )

    return geolocation


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


def get_ttl_for_cache_control_header_for_suggestions(
    request_providers: list[BaseProvider], suggestions: list[BaseSuggestion]
) -> int:
    """Retrieve the TTL value for the Cache-Control header based on provider and suggestions
    type. Return the default suggestions response ttl sec otherwise.
    """
    match request_providers:
        case [WeatherProvider()]:
            match suggestions:
                # this case targets accuweather suggestions and pulls out the ttl and then
                # deletes the custom_details attribute to be not included in the response
                case [
                    WeatherSuggestion(
                        custom_details=CustomDetails(
                            weather=WeatherDetails(weather_report_ttl=ttl)
                        )
                    ) as suggestion
                ]:
                    delattr(suggestion, "custom_details")
                    return ttl
                case _:
                    # can add a use case for some other type of suggestion
                    return DEFAULT_CACHE_CONTROL_TTL
        case _:
            # can add a use case for some other type of provider
            return DEFAULT_CACHE_CONTROL_TTL
