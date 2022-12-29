"""Weather integration."""
import logging
from typing import Any, Optional, Protocol

from pydantic import BaseModel, HttpUrl

from merino.backends.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

logger = logging.getLogger(__name__)


class Temperature(BaseModel):
    """Model for temperature with C and F values."""

    c: Optional[float] = None
    f: Optional[float] = None

    def __init__(self, c: Optional[float] = None, f: Optional[float] = None):
        super().__init__(c=c, f=f)
        if c is None and f is not None:
            self.c = round((f - 32) * 5 / 9, 1)
        if f is None and c is not None:
            self.f = round(c * 9 / 5 + 32)


class CurrentConditions(BaseModel):
    """Model for weather current conditions."""

    url: HttpUrl
    summary: str
    icon_id: int
    temperature: Temperature


class Forecast(BaseModel):
    """Model for weather one-day forecasts."""

    url: HttpUrl
    summary: str
    high: Temperature
    low: Temperature


class WeatherReport(BaseModel):
    """Model for weather conditions."""

    city_name: str
    current_conditions: CurrentConditions
    forecast: Forecast


class Suggestion(BaseSuggestion):
    """Model for weather suggestions."""

    city_name: str
    current_conditions: CurrentConditions
    forecast: Forecast


class WeatherBackend(Protocol):
    """Protocol for a weather backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:  # pragma: no cover
        """Get weather information from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...


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
