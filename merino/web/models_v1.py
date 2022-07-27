from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class ProviderResponse(BaseModel):
    """
    Model for the `providers` API response.
    """

    id: str
    availability: str


class BaseSuggestion(BaseModel):
    """
    Base model for suggestions, can be extended for sponsored and nonsponsored
    suggestions.
    """

    block_id: int
    full_keyword: str
    title: str
    url: HttpUrl
    advertiser: str
    provider: str
    is_sponsored: bool
    icon: HttpUrl
    score: float


class SponsoredSuggestion(BaseSuggestion):
    """
    Model for sponsored suggestions.
    """

    impression_url: HttpUrl
    click_url: HttpUrl


class NonsponsoredSuggestion(BaseSuggestion):
    """
    Model for nonsponsored suggestions.

    Both `impression_url` and `click_url` are optional compared to sponsored suggestions.
    """

    impression_url: Optional[HttpUrl] = None
    click_url: Optional[HttpUrl] = None


class SuggestResponse(BaseModel):
    """
    Model for the `suggest` API response.
    """

    suggestions: list[SponsoredSuggestion | NonsponsoredSuggestion]
    client_variants: list[str] = []
    server_variants: list[str] = []
    request_id: UUID = Field(default_factory=uuid4)
