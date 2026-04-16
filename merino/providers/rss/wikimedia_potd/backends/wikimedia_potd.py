"""Wikimedia Picture of the Day backend."""

from urllib.parse import urlparse, urlunparse

import aiodogstatsd
import feedparser
from bs4 import BeautifulSoup, Tag
from feedparser import FeedParserDict
from httpx import AsyncClient, Response
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
        return await self.fetch_picture_of_the_day()

    def _parse_description_html(self, html: str) -> tuple[str, str, str]:
        """Parse the RSS entry description HTML to extract image URLs and text.

        Returns:
            A tuple of (thumbnail_url, high_res_url, description_text).
        """
        soup = BeautifulSoup(html, "html.parser")

        img = soup.find("img")

        src = img.get("src") if isinstance(img, Tag) else None
        thumbnail_url: str = src if isinstance(src, str) else ""

        parsed = urlparse(thumbnail_url)
        parts = parsed.path.split("/")
        if "thumb" in parts:
            parts.remove("thumb")
            parts.pop()
        high_res_url = urlunparse(parsed._replace(path="/".join(parts)))

        desc_div = soup.find("div", class_="description")
        description_text = desc_div.get_text(separator=" ", strip=True) if desc_div else ""

        return thumbnail_url, high_res_url, description_text

    async def fetch_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Fetch Wikimedia Commons picture of the day RSS feed."""
        feed: Response = await self.http_client.get(
            self.feed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Merino/1.0; +https://github.com/mozilla-services/merino-py)"
            },
        )

        feed.raise_for_status()

        if not feed.content:
            return None

        parsed_feed: FeedParserDict = feedparser.parse(feed.text)

        if not parsed_feed.entries:
            return None

        # last item in the list is the latest picture of the day.
        potd = parsed_feed.entries[-1]
        title = str(potd.title)
        published_date = str(potd.published)

        thumbnail_url, high_res_url, description = self._parse_description_html(
            str(potd.description)
        )

        return PictureOfTheDay(
            title=title,
            thumbnail_image_url=HttpUrl(thumbnail_url),
            high_res_image_url=HttpUrl(high_res_url),
            description=description,
            published_date=published_date,
        )
