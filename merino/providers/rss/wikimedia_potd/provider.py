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

    async def get_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Return the Wikimedia Picture of the Day, or None if none has ever been cached.

        Re-fetches when the cached potd is missing or from a previous day. When today's
        potd isn't available yet we serve the previous day's cached potd rather than
        nothing.
        """
        if not self._is_todays_potd(self.potd):
            await self._refresh_potd()

        # TODO @herraj jira: [HNT-2162]
        # add a metric to track when we serve a stale (previous-day) potd here
        # because today's picture isn't yet available in the gcs bucket.
        return self.potd

    async def upload_picture_of_the_day(self) -> bool:
        """Execute the upload flow. This method is called by the job cli command only."""
        return await self.backend.upload_picture_of_the_day()

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
