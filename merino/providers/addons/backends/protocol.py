"""Addon Base Models and Protocol."""
from typing import Protocol

from pydantic import BaseModel

from merino.providers.addons.addons_data import SupportedAddons


class Addon(BaseModel):
    """Interface object between Backend and Provider."""

    name: str
    description: str
    url: str
    icon: str
    rating: str


class AddonsBackend(Protocol):
    """Addon Protocol."""

    async def get_addon(self, addon_key: SupportedAddons) -> Addon:  # pragma: no cover
        """Get an Addon based on the addon_key"""

    async def initialize_addons(self) -> None:
        """Initialize addons to be stored."""
