"""Wikimedia Picture of the Day provider."""

import logging
import aiodogstatsd
from pydantic import HttpUrl

from merino.providers.rss.base import BaseRssProvider
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    Potd,
    WikimediaPotdBackend,
)

logger = logging.getLogger(__name__)


class WikimediaPotdProvider(BaseRssProvider):
    """Provider for the Wikimedia Picture of the Day feed."""

    backend: WikimediaPotdBackend
    metrics_client: aiodogstatsd.Client
    url: HttpUrl
    manifest_data: None

    def __init__(
        self,
        backend: WikimediaPotdBackend,
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
        self.manifest_data = None

    async def initialize(self) -> None:
        """Initialize the provider."""

    async def get_picture_of_the_day(self) -> Potd:
        """Return the current Wikimedia Picture of the Day."""
        potd = await self.backend.get_picture_of_the_day()
        return potd if potd is not None else Potd(title="", image_url="")

    async def shutdown(self) -> None:
        """Shut down the provider."""
