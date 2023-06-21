"""Protocol for weather provider backends."""
from typing import Optional, Protocol

from pydantic import BaseModel, HttpUrl

from merino.middleware.geolocation import Location


class Temperature(BaseModel):
    """Model for temperature with C and F values."""

    c: Optional[float] = None
    f: Optional[float] = None

    def __init__(self, c: Optional[float] = None, f: Optional[float] = None):
        super().__init__(c=c, f=f)
        if c is not None:
            self.c = round(c)
            if f is None:
                self.f = round(c * 9 / 5 + 32)
        if f is not None:
            self.f = round(f)
            if c is None:
                self.c = round((f - 32) * 5 / 9)


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

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
