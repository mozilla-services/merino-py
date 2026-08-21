"""Protocol for yelp provider backends."""

from typing import Protocol, Any

from pydantic import HttpUrl, BaseModel


class YelpBusinessDetails(BaseModel):
    """Yelp business details."""

    name: str
    url: HttpUrl
    city: str
    address: str | None = None
    price: str | None = None
    rating: float | None = None
    review_count: int | None = None
    business_hours: dict[str, Any] | None = None
    image_url: str | None = None


class YelpBackendProtocol(Protocol):
    """Protocol for a yelp backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...

    async def get_business(self, search_term, location) -> dict | None:
        """Return Yelp business."""
        ...
