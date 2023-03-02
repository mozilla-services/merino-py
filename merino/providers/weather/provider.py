"""Weather integration."""
import hashlib
import json
import logging
from datetime import timedelta
from typing import Any, Optional

import aiodogstatsd

from merino.cache.protocol import CacheAdapter
from merino.exceptions import (
    BackendError,
    CacheAdapterError,
    CacheEntryError,
    CacheMissError,
)
from merino.middleware.geolocation import Location
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
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


class Provider(BaseProvider):
    """Suggestion provider for weather."""

    backend: WeatherBackend
    cache: CacheAdapter
    metrics_client: aiodogstatsd.Client
    score: float
    cached_report_ttl_sec: int

    def __init__(
        self,
        backend: WeatherBackend,
        cache: CacheAdapter,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        cached_report_ttl_sec: int,
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.cache = cache
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self.cached_report_ttl_sec = cached_report_ttl_sec
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    def cache_key_for_weather_report(self, geolocation: Location) -> Optional[str]:
        """Compute a Redis key used to look up and store cached weather reports for a location."""
        cache_inputs: Optional[bytes] = self.backend.cache_inputs_for_weather_report(
            geolocation
        )
        if not cache_inputs:
            return None

        return f"{self.name}:v1:report:{hashlib.blake2s(cache_inputs).hexdigest()}"

    async def fetch_cached_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:
        """Fetch a cached weather report, if available, for a location.

        Raises:
            - `CacheMissError` if there's no entry in the cache for this location.
            - `CacheEntryError` if the cached weather report can't be deserialized.
        """
        with self.metrics_client.timeit(f"providers.{self.name}.query.cache.fetch"):
            cache_key: Optional[str] = self.cache_key_for_weather_report(geolocation)
            if not cache_key:
                raise CacheMissError

            cache_value: Optional[bytes] = await self.cache.get(cache_key)
            if not cache_value:
                raise CacheMissError

            try:
                weather_report_dict = json.loads(cache_value)
                if not weather_report_dict:
                    return None
                return WeatherReport.parse_obj(weather_report_dict)
            except ValueError as exc:
                # `ValueError` is the common superclass of `json.JSONDecodeError` and
                # `pydantic.ValidationError`.
                raise CacheEntryError("Failed to parse cache entry") from exc

    async def store_cached_weather_report(
        self, geolocation: Location, weather_report: Optional[WeatherReport]
    ):
        """Store a cached weather report, or the absence of one, for a location."""
        with self.metrics_client.timeit(f"providers.{self.name}.query.cache.store"):
            cache_key: Optional[str] = self.cache_key_for_weather_report(geolocation)
            if not cache_key:
                return

            # If the request to the backend succeeded, but didn't return a report, we want to
            # negatively cache an empty value, so that subsequent requests for that location won't
            # make additional backend calls every time. This case is separate from a transient
            # backend error, which isn't negatively cached.
            cache_value = (
                weather_report.json().encode("utf-8") if weather_report else b"{}"
            )
            await self.cache.set(
                cache_key,
                cache_value,
                ttl=timedelta(seconds=self.cached_report_ttl_sec),
            )

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide weather suggestions."""
        geolocation: Location = srequest.geolocation
        weather_report: Optional[WeatherReport] = None

        try:
            weather_report = await self.fetch_cached_weather_report(geolocation)
            self.metrics_client.increment(f"providers.{self.name}.query.cache.hit")
        except (CacheAdapterError, CacheEntryError, CacheMissError) as exc:
            if isinstance(exc, CacheMissError):
                self.metrics_client.increment(f"providers.{self.name}.query.cache.miss")
            else:
                self.metrics_client.increment(
                    f"providers.{self.name}.query.cache.error"
                )
                logger.warning(f"Failed to load cached weather report: {exc}")
            try:
                with self.metrics_client.timeit(
                    f"providers.{self.name}.query.backend.get"
                ):
                    weather_report = await self.backend.get_weather_report(geolocation)
                try:
                    await self.store_cached_weather_report(geolocation, weather_report)
                except CacheAdapterError as exc:
                    self.metrics_client.increment(
                        f"providers.{self.name}.query.cache.error"
                    )
                    logger.warning(f"Failed to store cached weather report: {exc}")
            except BackendError as backend_error:
                logger.warning(backend_error)

        if weather_report is None:
            return []
        return [
            Suggestion(
                title=f"Weather for {weather_report.city_name}",
                url=weather_report.current_conditions.url,
                provider=self.name,
                is_sponsored=False,
                score=self.score,
                icon=None,
                city_name=weather_report.city_name,
                current_conditions=weather_report.current_conditions,
                forecast=weather_report.forecast,
            )
        ]

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.cache.close()
