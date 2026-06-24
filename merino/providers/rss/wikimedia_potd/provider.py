"""Wikimedia Picture of the Day provider."""

import logging
import aiodogstatsd
import asyncio
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

    async def initialize(self) -> None:
        """Initialize the provider."""
        if self.potd is None:
            # fetch potd from the gcs bucket instead
            self.potd = await asyncio.to_thread(self.backend.fetch_potd_from_gcs_bucket)

    def get_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Return the current Wikimedia Picture of the Day or None."""
        return self.potd

    async def shutdown(self) -> None:
        """Shut down the provider."""
        # TODO
