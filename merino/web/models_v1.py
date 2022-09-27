"""Suggest and Provider Models"""
from pydantic import BaseModel

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
