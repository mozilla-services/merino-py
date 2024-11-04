"""Protocol and Pydantic models for Fakespot."""

from pydantic import BaseModel
from typing import Protocol

from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId

# Fakespot UI copy - hardcoded strings for now.
FAKESPOT_DEFAULT_CATEGORY_NAME = "Holiday Gift Guide"
FAKESPOT_HEADER_COPY = (
    "Fakespot by Mozilla checks the reliability of product reviews so you don't have to."
)
FAKESPOT_FOOTER_COPY = "Take the guesswork out of gifting with Fakespot's 2024 Gift Guide."
FAKESPOT_CTA_COPY = "Explore more gifts"
FAKESPOT_CTA_URL = "https://www.fakespot.com/giftguide/holidays2024/"
# allowed locale for now
FAKESPOT_CACHE_KEY = ScheduledSurfaceId.NEW_TAB_EN_US


class FakespotProduct(BaseModel):
    """Fakespot product details"""

    id: str
    title: str
    category: str
    imageUrl: str
    url: str


class FakespotCTA(BaseModel):
    """Fakespot CTA"""

    ctaCopy: str
    url: str


class FakespotFeed(BaseModel):
    """Fakespot product recommendations"""

    products: list[FakespotProduct]
    defaultCategoryName: str
    headerCopy: str
    footerCopy: str
    cta: FakespotCTA


class FakespotBackend(Protocol):
    """Protocol for Fakespot backend that the provider depends on."""

    def get(self, key: str) -> FakespotFeed | None:
        """Fetch fakespot feed"""
        ...

    @property
    def update_count(self) -> int:
        """Returns the number of times the products have been updated."""
        ...
