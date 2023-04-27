"""Addons Provider"""
from typing import Any

from merino.config import settings
from merino.providers.addons.backends.protocol import Addon, AddonsBackend
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import AddonsDetails, CustomDetails


class TemporaryAddonSuggestion(BaseSuggestion):
    """Temporarily returning this is_top_pick flag so that it renders as top pick.
    Will remove this once the UX is released so that it can pick just the addon provider.
    """

    is_top_pick: bool = True


def invert_and_expand_index_keywords(
    keywords: dict[str, set[str]],
    min_chars: int,
) -> dict[str, str]:
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
    """Provider for Addons"""

    score: float
    backend: AddonsBackend
    addon_keywords: dict[str, str]
    keywords: dict[str, set[str]]
    min_chars: int

    def __init__(
        self,
        backend: AddonsBackend,
        keywords: dict[str, set[str]],
        name: str = "addons",
        enabled_by_default: bool = True,
        min_chars=settings.providers.addons.min_chars,
        score=settings.providers.addons.score,
        **kwargs: Any
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
        await self.backend.initialize_addons()
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

        addon: Addon = await self.backend.get_addon(matched_addon)

        return [
            TemporaryAddonSuggestion(
                title=addon.name,
                description=addon.description,
                url=addon.url,
                score=self.score,
                is_sponsored=True,
                provider=self.name,
                icon=addon.icon,
                custom_details=CustomDetails(addons=AddonsDetails(rating=addon.rating)),
            )
        ]
