"""Protocol for Kayak provider backend."""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

TravelVertical = Literal["hotels", "flights", "cars"]


class TravelListing(BaseModel):
    """Model for a travel listing"""

    name: str = Field(description="Localised name of the place, e.g. airport or city name")
    full_name: str = Field(
        description="Localised full name, may include city, region, country and airport name"
    )
    type: str = Field(description="Primary place type of the place, e.g. `city` or `airport`")
    iata_code: str | None = Field(
        default=None, description="IATA code for the airport or metro area"
    )
    place_id: int = Field(description="Kayak's unique identifier of the place")
    city_id: int | None = Field(default=None, description="Kayak's identifier of the city")
    country: str | None = Field(default=None, description="Localised country name of the place")


class TravelBackend(Protocol):
    """Protocol for a travel backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get_listings(
        self, query: str, locale: str, vertical: TravelVertical
    ) -> list[TravelListing]:
        """Fetch travel listings for the given query, locale and vertical."""
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
