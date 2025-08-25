"""Custom Details specific Models"""

from pydantic import BaseModel

from merino.middleware.geolocation import Coordinates
from merino.providers.suggest.finance.backends.protocol import TickerSummary


class AmoDetails(BaseModel):
    """Addon specific fields."""

    rating: str
    number_of_ratings: int
    guid: str


class GeolocationDetails(BaseModel):
    """Geolocation specific fields."""

    country: str | None = None
    country_code: str | None = None
    region_code: str | None = None
    region: str | None = None
    city: str | None = None
    location: Coordinates | None = None


class WeatherDetails(BaseModel):
    """Weather specific fields."""

    weather_report_ttl: int


class PolygonDetails(BaseModel):
    """Polygon specific fields."""

    values: list[TickerSummary]


class YelpDetails(BaseModel):
    """Yelp specific fields."""

    name: str
    address: str | None = None
    price: str | None = None
    rating: float | None = None
    review_count: int | None = None
    business_hours: list[dict] | None = None


class CustomDetails(BaseModel, arbitrary_types_allowed=False):
    """Contain references to custom fields for each provider.
    This object uses the provider name as the key, and references custom schema models.
    Please consult the custom details object for more information.
    """

    amo: AmoDetails | None = None
    geolocation: GeolocationDetails | None = None
    weather: WeatherDetails | None = None
    polygon: PolygonDetails | None = None
    yelp: YelpDetails | None = None
