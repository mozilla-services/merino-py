"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
import feedparser
from pydantic import HttpUrl
from feedparser import FeedParserDict
from httpx import AsyncClient, HTTPError, Response

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
from merino.providers.rss.wikimedia_potd.backends.utils import (
    extract_potd,
    RSS_FETCH_REQUEST_HEADERS,
)
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)


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
        # TODO: remove when ready to fetch from live rss feed.
        # potd = await self.fetch_picture_of_the_day()

        # if potd is None:
        #     return None
        # else:
        #     return parse_potd(potd=potd)
        return PictureOfTheDay(
            title="Wikimedia Commons picture of the day",
            thumbnail_image_url=HttpUrl(
                "https://prod-images.merino.prod.webservices.mozgcp.net/rss/wikimedia_potd/POTD_2026_04_13.jpg"
            ),
            high_res_image_url=HttpUrl(
                "https://prod-images.merino.prod.webservices.mozgcp.net/rss/wikimedia_potd/POTD_hi_res_2026_4_13.jpg"
            ),
            published_date="Mon, 13 Apr 2026 00:00:00 GMT",
            description="Sample Picture of the day description.",
        )

    async def fetch_picture_of_the_day(self) -> FeedParserDict | None:
        """Fetch Wikimedia Commons picture of the day RSS feed."""
        try:
            feed: Response = await self.http_client.get(
                self.feed_url, headers=RSS_FETCH_REQUEST_HEADERS
            )

            feed.raise_for_status()

            if not feed.content:
                return None

            parsed_feed: FeedParserDict = feedparser.parse(feed.text)

            return extract_potd(parsed_feed)
        except HTTPError as ex:
            logger.error(f"HTTP error occurred when fetching Wikimedia POTD feed: {ex}")
            return None
