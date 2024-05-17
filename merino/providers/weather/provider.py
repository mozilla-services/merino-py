"""Weather integration."""

import logging
from typing import Any

import aiodogstatsd
from pydantic import HttpUrl

from merino.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.weather.backends.accuweather import LocationCompletion
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    WeatherBackend,
    WeatherReport,
)

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for weather suggestions."""

    city_name: str
    current_conditions: CurrentConditions
    forecast: Forecast


class LocationCompletionSuggestion(BaseSuggestion):
    """Model for location completion suggestion."""

    locations: list[LocationCompletion]


class Provider(BaseProvider):
    """Suggestion provider for weather."""

    backend: WeatherBackend
    metrics_client: aiodogstatsd.Client
    score: float
    dummy_url: HttpUrl

    def __init__(
        self,
        backend: WeatherBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
        dummy_url: str = "https://merino.services.mozilla.com/",
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.dummy_url = HttpUrl(dummy_url)
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide weather suggestions."""
        geolocation: Location = srequest.geolocation
        is_location_completion_request = srequest.request_type == "location"
        weather_report: WeatherReport | None = None
        location_completions: list[LocationCompletion] | None = None

        try:
            with self.metrics_client.timeit(f"providers.{self.name}.query.backend.get"):
                if is_location_completion_request:
                    location_completions = await self.backend.get_location_completion(
                        geolocation, search_term=srequest.query
                    )
                else:
                    weather_report = await self.backend.get_weather_report(geolocation)

        except BackendError as backend_error:
            logger.warning(backend_error)

        # for this provider, the request can be either for weather or location completion
        if weather_report:
            return [self.build_suggestion(weather_report)]
        if location_completions:
            print("\n------ PROVIDER")
            print(f"{location_completions}")
            print("\n")
            return [self.build_suggestion(location_completions)]
        else:
            return []

    def build_suggestion(
        self, data: WeatherReport | list[LocationCompletion]
    ) -> Suggestion | LocationCompletionSuggestion:
        """Build either a weather suggestion or a location completion suggestion."""
        if isinstance(data, WeatherReport):
            return Suggestion(
                title=f"Weather for {data.city_name}",
                url=data.current_conditions.url,
                provider=self.name,
                is_sponsored=False,
                score=self.score,
                icon=None,
                city_name=data.city_name,
                current_conditions=data.current_conditions,
                forecast=data.forecast,
                custom_details=CustomDetails(
                    weather=WeatherDetails(weather_report_ttl=data.ttl)
                ),
            )
        else:
            return LocationCompletionSuggestion(
                title="Location completions",
                url=self.dummy_url,
                provider=self.name,
                is_sponsored=False,
                score=self.score,
                icon=None,
                locations=data,
            )

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
