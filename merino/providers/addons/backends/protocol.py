"""Addon Base Models and Protocol."""
from typing import Protocol

from pydantic import BaseModel


class Addon(BaseModel):
    """Interface object between Backend and Provider."""

    name: str
    description: str
    url: str
    icon: str
    rating: str


class AddonsBackend(Protocol):
    """Addon Protocol."""

    async def get_addon(self, addon_key: str) -> Addon:  # pragma: no cover
        """Get Addon based on addon_key"""
