"""Weather integration."""

import asyncio
import logging
from typing import Any, Optional

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.weather.backends.accuweather.errors import (
    MissingLocationKeyError,
)
from merino.governance.circuitbreakers import WeatherCircuitBreaker
from merino.utils import cron
from merino.middleware.geolocation import Location
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import CustomDetails, WeatherDetails
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    get_region_mapping_size,
    get_skip_cities_mapping_total,
    get_skip_cities_mapping_size,
)
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    HourlyForecastsWithTTL,
    LocationCompletion,
    WeatherBackend,
    WeatherReport,
    WeatherContext,
    Temperature,
)

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for weather suggestions."""

    city_name: str
    region_code: str
    current_conditions: CurrentConditions
    forecast: Forecast
    placeholder: Optional[bool] = None


# A sentinel suggestion indicating that no location key was found for the given location.
NO_LOCATION_KEY_SUGGESTION: Suggestion = Suggestion(
    title="N/A",
    url=HttpUrl("https://merino.services.mozilla.com"),
    city_name="",
    region_code="",
    current_conditions=CurrentConditions(
        url=HttpUrl("https://merino.services.mozilla.com"),
        icon_id=0,
        summary="",
        temperature=Temperature(),
    ),
    forecast=Forecast(
        url=HttpUrl("https://merino.services.mozilla.com"),
        summary="",
        high=Temperature(),
        low=Temperature(),
    ),
    provider="",
    is_sponsored=False,
    score=0,
    placeholder=True,
)


class LocationCompletionSuggestion(BaseSuggestion):
    """Model for location completion suggestion."""

    locations: list[LocationCompletion]


class Provider(BaseProvider):
    """Suggestion provider for weather."""

    backend: WeatherBackend
    metrics_client: aiodogstatsd.Client
    score: float
    dummy_url: HttpUrl
    cron_task: asyncio.Task
    cron_interval_sec: float

    def __init__(
        self,
        backend: WeatherBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        cron_interval_sec: float,
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
        self.cron_interval_sec = cron_interval_sec
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        cron_job = cron.Job(
            name="fetch_location_info",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch_mappings,
        )
        self.cron_task = asyncio.create_task(cron_job())

    def hidden(self) -> bool:  # noqa: D102
        return False

    def _should_fetch(self) -> bool:
        return True

    async def _fetch_mappings(self) -> None:
        self.metrics_client.gauge(
            name=f"providers.{self.name}.pathfinder.mapping.size",
            value=get_region_mapping_size(),
        )
        self.metrics_client.gauge(
            name=f"providers.{self.name}.skip_cities_mapping.total.size",
            value=get_skip_cities_mapping_total(),
        )
        self.metrics_client.gauge(
            name=f"providers.{self.name}.skip_cities_mapping.unique.size",
            value=get_skip_cities_mapping_size(),
        )

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if srequest.query and not srequest.request_type:
            logger.warning("HTTP 400: invalid query parameters: `request_type` is missing")
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `request_type` is missing",
            )

    @WeatherCircuitBreaker(name="weather")  # Expect `AccuweatherError` and `BackendError`
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide weather suggestions.

        All the `AccuweatherError` errors, raised from the backend, are intentionally
        unhandled in this function to drive the circuit breaker. Those exceptions will
        eventually be propagated to the provider consumer (i.e. the API handler) and be
        handled there.
        """
        geolocation: Location = srequest.geolocation
        languages: list[str] = srequest.languages if srequest.languages else []
        source: Optional[str] = srequest.source
        is_location_completion_request = srequest.request_type == "location"
        weather_report: WeatherReport | None = None
        location_completions: list[LocationCompletion] | None = None
        weather_context = WeatherContext(geolocation, languages, request_source=source)
        is_soft_pii: bool = srequest.is_soft_pii
        try:
            with self.metrics_client.timeit(f"providers.{self.name}.query.backend.get"):
                if is_location_completion_request and is_soft_pii:
                    # location requests aren't location keys so they shouldn't contain pii
                    return []
                if is_location_completion_request:
                    location_completions = await self.backend.get_location_completion(
                        weather_context, search_term=srequest.query
                    )
                else:
                    tags = {"source": srequest.source if srequest.source else "newtab"}
                    weather_context.geolocation.key = srequest.query
                    self.metrics_client.increment(
                        f"providers.{self.name}.query.weather_report", tags=tags
                    )
                    weather_report = await self.backend.get_weather_report(weather_context)
        except MissingLocationKeyError:
            return [NO_LOCATION_KEY_SUGGESTION]

        # for this provider, the request can be either for weather or location completion
        if weather_report:
            return [self.build_suggestion(weather_report)]
        if location_completions:
            return [self.build_suggestion(location_completions)]
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
                region_code=data.region_code,
                current_conditions=data.current_conditions,
                forecast=data.forecast,
                custom_details=CustomDetails(weather=WeatherDetails(weather_report_ttl=data.ttl)),
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

    async def get_hourly_forecasts(
        self, weather_context: WeatherContext
    ) -> HourlyForecastsWithTTL | None:
        """Provide hourly forecasts."""
        try:
            hourly_forecsts_with_ttl: (
                HourlyForecastsWithTTL | None
            ) = await self.backend.get_hourly_forecasts(weather_context)
        except (MissingLocationKeyError, Exception):
            # TODO @herraj remove exception when adding circuit breaker
            return None

        return hourly_forecsts_with_ttl

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
