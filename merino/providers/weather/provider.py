"""Weather integration."""
import logging
from typing import Any, Optional

from merino.exceptions import BackendError
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

    def __init__(
        self,
        backend: WeatherBackend,
        score: float,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide weather suggestions."""
        geolocation: Location = srequest.geolocation
        weather_report: Optional[WeatherReport] = None
        try:
            weather_report = await self.backend.get_weather_report(geolocation)
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
