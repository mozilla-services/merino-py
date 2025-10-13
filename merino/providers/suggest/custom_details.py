"""Custom Details specific Models"""

from pydantic import BaseModel

from merino.middleware.geolocation import Coordinates
from merino.providers.suggest.finance.backends.protocol import TickerSummary
from merino.providers.suggest.google_suggest.backends.protocol import (
    GoogleSuggestResponse,
)
from merino.providers.suggest.flightaware.backends.protocol import FlightSummary
from merino.providers.suggest.yelp.backends.protocol import YelpBusinessDetails

from merino.providers.suggest.sports.backends.sportsdata.protocol import SportSummary


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


class FlightAwareDetails(BaseModel):
    """FlightAware specific fields."""

    values: list[FlightSummary]


class YelpDetails(BaseModel):
    """Yelp specific fields."""

    values: list[YelpBusinessDetails]


class GoogleSuggestDetails(BaseModel):
    """Google Suggest specific fields."""

    suggestions: GoogleSuggestResponse


class SportDetails(BaseModel):
    """SportsData Sport event fields."""

    values: list[SportSummary]


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
    google_suggest: GoogleSuggestDetails | None = None
    sports: SportDetails | None = None
    flightaware: FlightAwareDetails | None = None
