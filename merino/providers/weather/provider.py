"""Weather integration."""

import asyncio
import logging
from typing import Any

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.utils import cron
from merino.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.weather.backends.accuweather.pathfinder import (
    get_region_mapping_size,
    get_region_mapping,
    get_skip_cities_mapping_total,
    get_skip_cities_mapping_size,
    get_skip_cities_mapping,
)
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    LocationCompletion,
    WeatherBackend,
    WeatherReport,
    WeatherContext,
)

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for weather suggestions."""

    city_name: str
    region_code: str
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
        logger.info(f"Weather Successful Mapping Values: {get_region_mapping()}")

        self.metrics_client.gauge(
            name=f"providers.{self.name}.skip_cities_mapping.total.size",
            value=get_skip_cities_mapping_total(),
        )
        self.metrics_client.gauge(
            name=f"providers.{self.name}.skip_cities_mapping.unique.size",
            value=get_skip_cities_mapping_size(),
        )

        logger.info(f"Weather Skip Cities: {get_skip_cities_mapping()}")

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide weather suggestions."""
        # early exit with 400 error if "q" query param is present without the "request_type" param
        if srequest.query and not srequest.request_type:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `request_type` is missing",
            )

        geolocation: Location = srequest.geolocation
        languages: list[str] = srequest.languages if srequest.languages else []
        is_location_completion_request = srequest.request_type == "location"
        weather_report: WeatherReport | None = None
        location_completions: list[LocationCompletion] | None = None
        weather_context = WeatherContext(geolocation, languages)
        try:
            with self.metrics_client.timeit(f"providers.{self.name}.query.backend.get"):
                if is_location_completion_request:
                    location_completions = await self.backend.get_location_completion(
                        weather_context, search_term=srequest.query
                    )
                else:
                    weather_context.geolocation.key = srequest.query
                    weather_report = await self.backend.get_weather_report(weather_context)

        except BackendError as backend_error:
            logger.warning(backend_error)

        # for this provider, the request can be either for weather or location completion
        if weather_report:
            return [self.build_suggestion(weather_report)]
        if location_completions:
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

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
