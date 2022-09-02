"""Suggest and Provider Models"""
from typing import Optional

from pydantic import BaseModel, HttpUrl


class ProviderResponse(BaseModel):
    """Model for the `providers` API response."""

    id: str
    availability: str


class BaseSuggestion(BaseModel):
    """Base model for suggestions, can be extended for sponsored and
    nonsponsored suggestions.
    """

    block_id: int
    full_keyword: str
    title: str
    url: HttpUrl
    advertiser: str
    provider: str
    is_sponsored: bool
    score: float
    icon: str | None = None


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    impression_url: HttpUrl
    click_url: HttpUrl


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions.

    Both `impression_url` and `click_url` are optional compared to
    sponsored suggestions.
    """

    impression_url: Optional[HttpUrl] = None
    click_url: Optional[HttpUrl] = None


class SuggestResponse(BaseModel):
    """Model for the `suggest` API response."""

    suggestions: list[SponsoredSuggestion | NonsponsoredSuggestion]
    request_id: str
    client_variants: list[str] = []
    server_variants: list[str] = []
