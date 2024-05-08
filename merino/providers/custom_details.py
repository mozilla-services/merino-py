"""Custom Details specific Models"""
from pydantic import BaseModel


class AmoDetails(BaseModel):
    """Addon specific fields."""

    rating: str
    number_of_ratings: int
    guid: str


class GeolocationDetails(BaseModel):
    """Geolocation specific fields."""

    country: str | None = None
    region: str | None = None
    city: str | None = None


class WeatherDetails(BaseModel):
    """Weather specific fields."""

    weather_report_ttl: int


class CustomDetails(BaseModel, arbitrary_types_allowed=False):
    """Contain references to custom fields for each provider.
    This object uses the provider name as the key, and references custom schema models.
    Please consult the custom details object for more information.
    """

    amo: AmoDetails | None = None
    geolocation: GeolocationDetails | None = None
    weather: WeatherDetails | None = None
