"""Suggest and Provider Models"""

from pydantic import BaseModel, SerializeAsAny, HttpUrl
from typing import List

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


class Domain(BaseModel):
    """Model for the `domain` entry of the manifest file."""

    rank: int
    domain: str
    categories: List[str]
    serp_categories: List[int]
    url: HttpUrl
    title: str
    icon: str


class Manifest(BaseModel):
    """Model for the `manifest` API response."""

    domains: List[Domain]
