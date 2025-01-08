"""A utility module for merino API cache control."""

from merino.providers.base import BaseProvider, BaseSuggestion

from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.weather.provider import Provider as WeatherProvider
from merino.providers.weather.provider import Suggestion as WeatherSuggestion

from merino.configs.config import settings

# Default Cache-Control TTL value for /suggest endpoint responses
DEFAULT_CACHE_CONTROL_TTL: int = settings.runtime.default_suggestions_response_ttl_sec


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
