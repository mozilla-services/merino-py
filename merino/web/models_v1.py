"""Suggest and Provider Models"""
from pydantic import BaseModel, HttpUrl

from merino.providers.base import BaseSuggestion


class ProviderResponse(BaseModel):
    """Model for the `providers` API response."""

    id: str
    availability: str


class SuggestResponse(BaseModel):
    """Model for the `suggest` API response."""

    suggestions: list[BaseSuggestion]
    request_id: str
    client_variants: list[str] = []
    server_variants: list[str] = []


class HPKEResponse(BaseModel):
    """Model for the `hpke` API response."""

    pub_key: str


class InterestsSuggestion(BaseModel):
    """Suggestion model for the `interests` API response."""

    categories: str
    url: HttpUrl


class InterestsResponse(BaseModel):
    """Model for the `suggest` API response."""

    suggestions: list[InterestsSuggestion]


class InterestsRequest(BaseModel):
    """Model for the `interests` API request."""

    # base64 encoded encapsulated payload needed for HPKE.
    encapsulated: str
    # base64 encoded ciphertext.
    ciphertext: str
