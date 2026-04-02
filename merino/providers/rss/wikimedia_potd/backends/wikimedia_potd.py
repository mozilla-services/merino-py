"""Wikimedia Picture of the Day backend."""

import aiodogstatsd
from httpx import AsyncClient

from merino.providers.rss.wikimedia_potd.backends.protocol import Potd
from merino.utils.gcs.gcs_uploader import GcsUploader


class WikimediaPotdBackend:
    """Backend for fetching the Wikimedia Picture of the Day RSS feed."""

    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    gcs_uploader: GcsUploader

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        gcs_uploader: GcsUploader,
        feed_url: str,
    ) -> None:
        """Initialize the backend with the RSS feed URL."""
        self.feed_url = feed_url
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.gcs_uploader = gcs_uploader

    async def fetch(self) -> Potd | None:
        """Fetch the current Wikimedia Picture of the Day.

        Returns:
            A Potd instance if data is available, otherwise None.
        """
        return None
