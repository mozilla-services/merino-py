"""Protocol for weather provider backends."""

from typing import Protocol, Optional

from pydantic import BaseModel, HttpUrl

from merino.middleware.geolocation import Location

from dataclasses import dataclass


class Temperature(BaseModel):
    """Model for temperature with C and F values."""

    c: int | None = None
    f: int | None = None

    def __init__(self, c: float | None = None, f: float | None = None):
        cc: int | None = None
        ff: int | None = None
        if c is not None:
            cc = round(c)
            if f is None:
                ff = round(c * 9 / 5 + 32)
        if f is not None:
            ff = round(f)
            if c is None:
                cc = round((f - 32) * 5 / 9)
        super().__init__(c=cc, f=ff)


class LocationCompletionGeoDetails(BaseModel):
    """Model for a location completion's country and administrative area attributes."""

    id: str
    localized_name: str


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
    ttl: int
    region_code: str


class LocationCompletion(BaseModel):
    """Model for location completion."""

    key: str
    rank: int
    type: str
    localized_name: str
    country: LocationCompletionGeoDetails
    administrative_area: LocationCompletionGeoDetails


@dataclass
class WeatherContext:
    """Class that contains context needed to make weather reports."""

    geolocation: Location
    languages: list[str]
    selected_region: Optional[str] = None
    distance_calculation: Optional[bool] = None


class WeatherBackend(Protocol):
    """Protocol for a weather backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_weather_report(
        self, weather_context: WeatherContext
    ) -> WeatherReport | None:  # pragma: no cover
        """Get weather information from partner.

        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def get_location_completion(
        self, weather_context: WeatherContext, search_term: str
    ) -> list[LocationCompletion] | None:  # pragma: no cover
        """Get a list of locations (cities and country) from partner
        Raises:
            BackendError: Category of error specific to provider backends.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
