"""Addons Provider"""
import logging
from typing import Any

import pydantic

from merino.config import settings
from merino.providers.amo.addons_data import SupportedAddon
from merino.providers.amo.backends.protocol import Addon, AmoBackend, AmoBackendError
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import AmoDetails, CustomDetails

logger = logging.getLogger(__name__)


class AddonSuggestion(BaseSuggestion):
    """The Addon Suggestion"""

    # Temporarily returning this is_top_pick flag so that it renders as top pick.
    # Will remove this once the UX is released so that it can pick just the addon provider.
    is_top_pick: bool = pydantic.Field(True, const=True)

    # Addon Suggestions will always be Non-Sponsored
    is_sponsored: bool = pydantic.Field(False, const=True)


def invert_and_expand_index_keywords(
    keywords: dict[SupportedAddon, set[str]],
    min_chars: int,
) -> dict[str, SupportedAddon]:
    """Invert the keywords index.
    param keywords: mapping of addon key -> keywords
    returns: mapping of keyword -> addon key
    """
    inverted_index = {}
    for addon_name, kws in keywords.items():
        for word in kws:
            word = word.lower()
            # do the keyword expansion
            for i in range(min_chars, len(word) + 1):
                inverted_index[word[:i]] = addon_name
    return inverted_index


class Provider(BaseProvider):
    """Provider for Amo"""

    score: float
    backend: AmoBackend
    addon_keywords: dict[str, SupportedAddon]
    keywords: dict[SupportedAddon, set[str]]
    min_chars: int

    def __init__(
        self,
        backend: AmoBackend,
        keywords: dict[SupportedAddon, set[str]],
        name: str = "amo",
        enabled_by_default: bool = True,
        min_chars=settings.providers.amo.min_chars,
        score=settings.providers.amo.score,
        **kwargs: Any,
    ):
        """Initialize Addon Provider"""
        self._name = name
        self.score = score
        self.backend = backend
        self.min_chars = min_chars
        self.keywords = keywords
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize"""
        try:
            await self.backend.initialize_addons()
        except AmoBackendError as e:
            # Do not propagate the error as it can be recovered later by retrying.
            logger.warning(f"Failed to initialize addon backend: {e}")
        self.addon_keywords = invert_and_expand_index_keywords(
            self.keywords, self.min_chars
        )

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Given the query string, get the Addon that matches the keyword."""
        q: str = srequest.query
        if len(q) < self.min_chars:
            return []

        matched_addon = self.addon_keywords.get(q)

        if matched_addon is None:
            return []

        try:
            addon: Addon = await self.backend.get_addon(matched_addon)
        except AmoBackendError as ex:
            logger.error(f"Error getting AMO suggestion: {ex}")
            return []

        return [
            AddonSuggestion(
                title=addon.name,
                description=addon.description,
                url=addon.url,
                score=self.score,
                provider=self.name,
                icon=addon.icon,
                custom_details=CustomDetails(
                    amo=AmoDetails(
                        rating=addon.rating, number_of_ratings=addon.number_of_ratings
                    )
                ),
            )
        ]
