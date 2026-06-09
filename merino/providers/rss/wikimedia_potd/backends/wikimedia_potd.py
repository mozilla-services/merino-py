"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
import feedparser
from datetime import datetime
from pydantic import HttpUrl
from feedparser import FeedParserDict
from httpx import AsyncClient, HTTPError, Response, HTTPStatusError

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
from merino.utils.gcs.models import Image
from merino.providers.rss.wikimedia_potd.backends.utils import (
    extract_potd,
    RSS_FETCH_REQUEST_HEADERS,
)
from merino.utils.storage import get_storage_client
from gcloud.aio.storage import Storage
from sentry_sdk import capture_exception

logger = logging.getLogger(__name__)


class WikimediaPotdBackend:
    """Backend for fetching the Wikimedia Picture of the Day RSS feed."""

    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    gcs_client: Storage
    bucket_name: str
    cdn_hostname: str

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        feed_url: str,
        bucket_name: str,
        cdn_hostname: str,
    ) -> None:
        """Initialize the backend with the RSS feed URL."""
        self.feed_url = feed_url
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.gcs_client = get_storage_client()
        self.bucket_name = bucket_name
        self.cdn_hostname = cdn_hostname

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

    async def download_image(self, url: HttpUrl) -> Image | None:
        """Download the image using the image URL.

        Returns an Image object containing the binary content and content type,
        or None if no image URL is found.
        """
        # verify that the url is an image url
        if str(url).split(".")[-1] not in ["jpg", "jpeg", "png", "webp"]:
            return None

        try:
            # set up request headers to only accept image content types
            request_headers = {"Accept": "image/jpeg,image/png,image/webp"}
            response: Response = await self.http_client.get(str(url), headers=request_headers)
            response.raise_for_status()

            content = response.content
            content_type = response.headers["Content-Type"]

            return Image(
                content=content,
                content_type=str(content_type),
            )
        except HTTPStatusError as ex:
            # throw sentry exception for HTTP exceptions
            capture_exception(ex)
            return None
        except Exception as ex:
            # throw sentry exception for generic exceptions
            capture_exception(ex)
            return None

    async def upload_image(self, image: Image, is_thumbnail: bool) -> str:
        """Upload an image to the bucket."""
        folder_path_in_bucket = "rss/wikimedia_potd"

        # YYYY-MM-DD format
        date_time = datetime.today().strftime("%Y-%m-%d")

        prefix = "POTD"
        # append "_thumbnail" to the object name if it is a thumbnail image
        suffix = "thumbnail" if is_thumbnail else "hi_res"

        # extract image extension since the image.content_type has the format image/jpeg
        extension = image.content_type.split("/")[-1]

        # the path in the bucket for the image
        # would look like: "merino-images-prod/rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"
        object_name = f"{folder_path_in_bucket}/{prefix}_{date_time}_{suffix}.{extension}"

        await self.gcs_client.upload(
            bucket=self.bucket_name,
            object_name=object_name,
            file_data=image.content,
            content_type=image.content_type,
        )

        # TODO return public cdn image url
        return f"https://{self.cdn_hostname}/{object_name}"
