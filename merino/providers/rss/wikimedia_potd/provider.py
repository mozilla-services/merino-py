"""Wikimedia Picture of the Day provider."""

import logging
import aiodogstatsd
import asyncio
from datetime import datetime, timezone

import sentry_sdk
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
    _reported_stale_potd: bool

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
        # Track whether the current stale/missing window has already been reported, so we
        # emit at most one Sentry warning per window instead of one per request.
        self._reported_stale_potd = False

    @staticmethod
    def _today() -> str:
        """Return today's date (UTC) as a YYYY-MM-DD string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _is_todays_potd(self, potd: PictureOfTheDay | None) -> bool:
        """Return True when `potd` exists and was published today (UTC)."""
        return potd is not None and potd.published_date == self._today()

    async def _refresh_potd(self) -> None:
        """Fetch the potd from GCS and cache it when today's is available.

        On a miss (nothing fetched, or the fetched potd is from another day) the cached
        potd is left untouched and a single Sentry warning is emitted per stale window,
        which resets once today's potd is cached again.
        """
        fetched_potd = await asyncio.to_thread(self.backend.fetch_potd_from_gcs_bucket)

        # if today's potd is available, cache it and close the stale window
        if self._is_todays_potd(fetched_potd):
            self.potd = fetched_potd
            self._reported_stale_potd = False
            return

        # return if the stale window is open. Means that stale potd has been reported.
        if self._reported_stale_potd:
            return

        # open the stale window and report it once
        fetched_date = fetched_potd.published_date if fetched_potd is not None else "none"
        sentry_sdk.capture_message(
            f"Provider could not fetch a fresh potd for today from the gcs bucket. "
            f"Fetched published_date: {fetched_date}, today: {self._today()}",
            "warning",
        )
        self._reported_stale_potd = True

    async def initialize(self) -> None:
        """Initialize the provider by warming the potd cache."""
        if self.potd is not None:
            return

        await self._refresh_potd()

    async def get_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Return today's Wikimedia Picture of the Day or None.

        Re-fetches when the cached potd is missing or from a previous day. We intentionally
        do not throttle the re-fetch. A single Sentry warning per stale window surfaces the
        gap.
        """
        if not self._is_todays_potd(self.potd):
            await self._refresh_potd()

        return self.potd if self._is_todays_potd(self.potd) else None

    async def upload_picture_of_the_day(self) -> bool:
        """Execute the upload flow. This method is called by the job cli command only."""
        return await self.backend.upload_picture_of_the_day()

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
