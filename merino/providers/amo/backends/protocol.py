"""Addon Base Models and Protocol."""
from typing import Protocol

from pydantic import BaseModel

from merino.exceptions import BackendError
from merino.providers.amo.addons_data import SupportedAddon


class AmoBackendError(BackendError):
    """AMO Specific Errors"""

    pass


class Addon(BaseModel):
    """Interface object between Backend and Provider."""

    name: str
    description: str
    url: str
    icon: str
    rating: str
    number_of_ratings: int
    guid: str


class AmoBackend(Protocol):
    """Addon Protocol."""

    async def get_addon(self, addon_key: SupportedAddon) -> Addon:  # pragma: no cover
        """Get an Addon based on the addon_key.
        Raise a `BackendError` if the addon key is missing.
        """

    async def initialize_addons(self) -> None:
        """Initialize addons to be stored."""
