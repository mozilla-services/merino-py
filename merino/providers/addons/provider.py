"""Addons Provider"""
from typing import Any

from merino.providers.addons.backends.protocol import Addon, AddonsBackend
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import AddonsDetails, CustomDetails


class TemporaryAddonSuggestion(BaseSuggestion):
    """Temporarily returning this is_top_pick flag so that it renders as top pick.
    Will remove this once the UX is released so that it can pick just the addon provider.
    """

    is_top_pick: bool = True


class Provider(BaseProvider):
    """Provider for Addons"""

    score: float
    backend: AddonsBackend
    addon_keywords: dict[str, str]
    min_chars: int

    def __init__(
        self,
        name: str,
        score: float,
        backend: AddonsBackend,
        min_chars: int,
        keywords: dict[str, set[str]],
        enabled_by_default: bool = True,
        **kwargs: Any
    ):
        """Initialize Addon Provider"""
        self._name = name
        self.score = score
        self.backend = backend
        self.min_chars = min_chars
        self.addon_keywords = self._reverse_and_expand_index_keywords(keywords)
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize"""
        pass

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

    def _reverse_and_expand_index_keywords(
        self, keywords: dict[str, set[str]]
    ) -> dict[str, str]:
        """Reverse the keywords index.
        param keywords: mapping of addon key -> keywords
        returns: mapping of keyword -> addon key
        """
        reverse_index = {}
        for (addon_name, kws) in keywords.items():
            for word in list(kws):
                word = word.lower()
                # do the keyword expansion
                for i in range(self.min_chars, len(word) + 1):
                    reverse_index[word[:i]] = addon_name
        return reverse_index
