"""Protocol for Kayak provider backend."""

from typing import Literal, Protocol

from pydantic import BaseModel, Field, HttpUrl

TravelVertical = Literal["hotels", "flights", "cars"]


class TravelListing(BaseModel):
    """Model for a travel listing"""

    title: str = Field(description="Display title of the listing")
    url: HttpUrl = Field(description="URL of the listing")


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
