"""Addons Provider"""

import asyncio
import logging
import time
from typing import Any, Literal

from pydantic import HttpUrl

from merino.utils import cron
from merino.configs import settings
from merino.providers.suggest.amo.addons_data import SupportedAddon
from merino.providers.suggest.amo.backends.protocol import (
    Addon,
    AmoBackend,
    AmoBackendError,
)
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import AmoDetails, CustomDetails

logger = logging.getLogger(__name__)


class AddonSuggestion(BaseSuggestion):
    """The Addon Suggestion"""

    # Temporarily returning this is_top_pick flag so that it renders as top pick.
    # Will remove this once the UX is released so that it can pick just the addon provider.
    is_top_pick: Literal[True] = True

    # Addon Suggestions will always be Non-Sponsored
    is_sponsored: Literal[False] = False


def invert_and_expand_index_keywords(
    keywords: dict[SupportedAddon, set[str]],
) -> dict[str, SupportedAddon]:
    """Invert the keywords index.
    param keywords: mapping of addon key -> keywords
    returns: mapping of keyword -> addon key
    """
    inverted_index = {}
    for addon_name, kws in keywords.items():
        for phrase in kws:
            phrase = phrase.lower()
            first_word = phrase.split()[0]
            inverted_index[first_word] = addon_name
            # do the keyword expansion
            for i in range(len(first_word), len(phrase) + 1):
                inverted_index[phrase[:i]] = addon_name
    return inverted_index


class Provider(BaseProvider):
    """Provider for Amo"""

    score: float
    backend: AmoBackend
    addon_keywords: dict[str, SupportedAddon]
    keywords: dict[SupportedAddon, set[str]]
    min_chars: int
    cron_task: asyncio.Task
    resync_interval_sec: int
    cron_interval_sec: int
    last_fetch_at: float | None

    def __init__(
        self,
        backend: AmoBackend,
        keywords: dict[SupportedAddon, set[str]],
        name: str = "amo",
        enabled_by_default: bool = False,
        min_chars=settings.providers.amo.min_chars,
        score=settings.providers.amo.score,
        resync_interval_sec=settings.providers.amo.resync_interval_sec,
        cron_interval_sec=settings.providers.amo.cron_interval_sec,
        **kwargs: Any,
    ):
        """Initialize Addon Provider"""
        self.provider_id = name
        self.score = score
        self.backend = backend
        self.min_chars = min_chars
        self.keywords = keywords
        self._enabled_by_default = enabled_by_default
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.last_fetch_at = None
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize by setting up a cron to fetch it every 24 hours."""
        cron_job = cron.Job(
            name="addon_sync",
            interval=self.cron_interval_sec,
            # We don't have any strict conditions for not updating AMO.
            # So, always return True so that the fetch is run.
            condition=self._should_fetch,
            task=self._fetch_addon_info,
        )
        self.cron_task = asyncio.create_task(cron_job())

        self.addon_keywords = invert_and_expand_index_keywords(self.keywords)

    def normalize_query(self, query: str) -> str:
        """Ensure query string is case insensitive."""
        return query.strip().lower()

    async def _fetch_addon_info(self) -> None:
        try:
            await self.backend.fetch_and_cache_addons_info()
            self.last_fetch_at = time.time()
        except AmoBackendError as e:
            # Do not propagate the error as it can be recovered later by retrying.
            logger.warning(f"Failed to fetch addon information: {e}")

    def _should_fetch(self) -> bool:
        if self.last_fetch_at:
            return (time.time() - self.last_fetch_at) >= self.resync_interval_sec
        return True  # Fetch AMO data if it's unclear if it's been synced yet.

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
                url=HttpUrl(addon.url),
                score=self.score,
                provider=self.name,
                icon=addon.icon,
                custom_details=CustomDetails(
                    amo=AmoDetails(
                        rating=addon.rating,
                        number_of_ratings=addon.number_of_ratings,
                        guid=addon.guid,
                    )
                ),
            )
        ]
