"""Custom Details specific Models"""

from typing import Any

from pydantic import BaseModel

from merino.middleware.geolocation import Coordinates
from merino.providers.suggest.finance.backends.protocol import TickerSummary
from merino.providers.suggest.google_suggest.backends.protocol import (
    GoogleSuggestResponse,
)
from merino.providers.suggest.flightaware.backends.protocol import FlightSummary
from merino.providers.suggest.yelp.backends.protocol import YelpBusinessDetails


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


class SportTeamDetails(BaseModel):
    """Data about the specific Sport team."""

    key: str  # Sport unique abbreviated identifier (e.g. "SFG", "DAL", etc)
    name: str  # Full name of the team
    colors: list[str]  # list of hex colors from primary to quaternary


class SportEventDetails(BaseModel):
    """Data about the specific Sport event."""

    sport: str  # Sport name abbreviation (e.g. "NFL", "NBA", "MBA", etc)
    id: int  # Unique game identifier
    date: int  # UTC timestamp for the game
    home_team: SportTeamDetails  # Home Team details
    away_team: SportTeamDetails  # Away Team details
    home_score: int | None  # Home team score (if applicable)
    away_score: int | None  # Away team score (if applicable)
    status: str  # English based game status string ("Scheduled", "In Progress", "Final", etc.)
    expiry: int  # UTC timestamp for when this record should no longer be shown

    @classmethod
    def from_event_dict(cls, event: dict[str, Any]):
        """Create an instance of SportEventDetails from a provided Event dictionary

        This presumes that it's reading a json loaded sport Event that was returned by elastic search.
        """
        return cls(
            sport=event.get("sport"),
            id=event.get("id"),
            date=event.get("date"),
            home_team=SportTeamDetails(
                key=event.get("home_team", {}).get("key"),
                name=event.get("home_team", {}).get("name"),
                colors=event.get("home_team", {}).get("colors"),
            ),
            away_team=SportTeamDetails(
                key=event.get("away_team", {}).get("key"),
                name=event.get("away_team", {}).get("name"),
                colors=event.get("away_team", {}).get("colors"),
            ),
            home_score=event.get("home_score"),
            away_score=event.get("away_score"),
            status=event.get("status"),
            expiry=event.get("expiry"),
        )


class SportsSuggestDetails(BaseModel):
    """SportsData Suggest Specific fields"""

    previous: SportEventDetails | None
    current: SportEventDetails | None
    next: SportEventDetails | None

    @classmethod
    def from_events(cls, events: dict[str, Any]):
        """Create a SportSuggestDetails instance off the returned result of a Sports query.

        This presumes that the query returns elements for the previous, current, and next events (as appropriate)
        """
        previous = current = next = None
        if events.get("previous"):
            previous = SportEventDetails.from_event_dict(events["previous"])
        if events.get("current"):
            previous = None
            current = SportEventDetails.from_event_dict(events["current"])
        if events.get("next"):
            next = SportEventDetails.from_event_dict(events["next"])
        return cls(
            previous=previous,
            current=current,
            next=next,
        )


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
    sports: SportsSuggestDetails | None = None
    flightaware: FlightAwareDetails | None = None
