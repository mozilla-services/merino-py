"""Suggest and Provider Models"""
from typing import List

from pydantic import BaseModel, SerializeAsAny

from merino.newtab.base import Recommendation
from merino.providers.base import BaseSuggestion


class ProviderResponse(BaseModel):
    """Model for the `providers` API response."""

    id: str
    availability: str


class SuggestResponse(BaseModel):
    """Model for the `suggest` API response."""

    # `SerializeAsAny` ensures that all fields of `BaseSuggestion` and its subclasses
    # (ex. provider-specific Suggestion classes) are included when converting this model
    # to a dictionary.  See Pydantic docs for context:
    # https://docs.pydantic.dev/latest/usage/serialization/#serializing-subclasses
    suggestions: list[SerializeAsAny[BaseSuggestion]]
    request_id: str | None = None
    client_variants: list[str] = []
    server_variants: list[str] = []


class NewTabResponse(BaseModel):
    """Model for the `newtab` API response."""

    data: List[Recommendation]
