"""Wikimedia Picture of the Day backend."""

import aiodogstatsd
from httpx import AsyncClient
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
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

    async def get_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Fetch the current Wikimedia Picture of the Day.

        Returns:
            A PictureOfTheDay instance if data is available, otherwise None.
        """
        # NOTE: These are hardcoded for now to unblock FE testing. The urls are public.
        # dynamic logic will be added in follow up work.
        return PictureOfTheDay(
            title="Wikimedia Commons picture of the day",
            thumbnail_image_url=HttpUrl(
                "https://storage.googleapis.com/merino-images-prod/rss/wikimedia_potd/POTD_2026_04_13.jpg"
            ),
            high_res_image_url=HttpUrl(
                "https://storage.googleapis.com/merino-images-prod/rss/wikimedia_potd/POTD_hi_res_2026_4_13.jpg"
            ),
            published_date="Mon, 13 Apr 2026 00:00:00 GMT",
        )
