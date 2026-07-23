"""Wikimedia Picture of the Day provider."""

import logging
import aiodogstatsd
import asyncio
from datetime import datetime, timezone

from pydantic import HttpUrl

from merino.providers.rss.base import BaseRssProvider
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPictureOfTheDayBackend,
)

logger = logging.getLogger(__name__)


class WikimediaPictureOfTheDayProvider(BaseRssProvider):
    """Provider for the Wikimedia Picture of the Day feed."""

    backend: WikimediaPictureOfTheDayBackend
    metrics_client: aiodogstatsd.Client
    url: HttpUrl
    potd: PictureOfTheDay | None

    def __init__(
        self,
        backend: WikimediaPictureOfTheDayBackend,
        metrics_client: aiodogstatsd.Client,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
    ) -> None:
        super().__init__(
            name=name, enabled_by_default=enabled_by_default, query_timeout_sec=query_timeout_sec
        )
        self.backend = backend
        self.metrics_client = metrics_client
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self.potd = None

    @staticmethod
    def _today() -> str:
        """Return today's date (UTC) as a YYYY-MM-DD string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _is_todays_potd(self, potd: PictureOfTheDay | None) -> bool:
        """Return True when `potd` exists and was published today (UTC)."""
        return potd is not None and potd.published_date == self._today()

    async def _refresh_potd(self) -> None:
        """Fetch the potd from GCS and cache whatever the bucket returns.

        When the fetch returns nothing (e.g. today's manifest hasn't been uploaded yet) the
        cached potd is left untouched, so a previously cached picture keeps being served.
        """
        fetched_potd = await asyncio.to_thread(self.backend.fetch_potd_from_gcs_bucket)

        if fetched_potd is not None:
            self.potd = fetched_potd

    async def initialize(self) -> None:
        """Initialize the provider by warming the potd cache."""
        if self.potd is not None:
            return

        await self._refresh_potd()

    @staticmethod
    def _select_description(
        potd: PictureOfTheDay, accepted_languages: list[str] | None
    ) -> str | None:
        """Return the best localized description for `accepted_languages`, or None.

        Each accepted language is matched against the potd's localized descriptions, trying
        the full code first (e.g. "pt-br") then the base subtag (e.g. "pt"), in the client's
        order of preference. Returns None when no localized description matches, so callers
        keep the default-language description already on the model.
        """
        if not accepted_languages or len(potd.localized_descriptions) == 0:
            return None

        for language in accepted_languages:
            code = language.lower()
            if code in potd.localized_descriptions:
                return potd.localized_descriptions[code]
            base = code.split("-")[0]
            if base in potd.localized_descriptions:
                return potd.localized_descriptions[base]

        return None

    async def get_picture_of_the_day(
        self, accepted_languages: list[str] | None = None
    ) -> PictureOfTheDay | None:
        """Return the Wikimedia Picture of the Day, or None if none has ever been cached.

        Re-fetches when the cached potd is missing or from a previous day. When today's
        potd isn't available yet we serve the previous day's cached potd rather than
        nothing. When `accepted_languages` matches a localized description, the returned
        potd's `description` is swapped for it; otherwise the default description is kept.
        """
        if not self._is_todays_potd(self.potd):
            await self._refresh_potd()

        # TODO @herraj jira: [HNT-2162]
        # add a metric to track when we serve a stale (previous-day) potd here
        # because today's picture isn't yet available in the gcs bucket.
        if self.potd is None:
            return None

        localized = self._select_description(self.potd, accepted_languages)

        if localized is not None:
            return self.potd.model_copy(update={"description": localized})

        return self.potd

    async def upload_picture_of_the_day(self) -> bool:
        """Execute the upload flow. This method is called by the job cli command only."""
        return await self.backend.upload_picture_of_the_day()

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
