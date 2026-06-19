"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
import feedparser
from pydantic import HttpUrl
from feedparser import FeedParserDict
from httpx import AsyncClient, HTTPError, Response

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.providers.rss.wikimedia_potd.backends.utils import (
    RSS_FETCH_REQUEST_HEADERS,
    extract_potd,
    parse_potd,
    build_potd_path_and_name,
    is_valid_potd_image_url,
)
import sentry_sdk

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
        feed_url: str,
        gcs_uploader: GcsUploader,
    ) -> None:
        """Initialize the backend with the RSS feed URL."""
        self.feed_url = feed_url
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.gcs_uploader = gcs_uploader

    async def get_picture_of_the_day(self) -> PictureOfTheDay | None:
        """Orchestrate the fetching from the RSS feed, downloading and uploading
        to the GCS bucket of thumbnail and hi-res version of the potd.

        Returns:
            A PictureOfTheDay instance if data is available, otherwise None.
        """
        # fetch the Wikimedia potd rss feed
        rss_potd = await self.fetch_picture_of_the_day()
        if rss_potd is None:
            return None

        # parse the feed to extract a PictureOfTheDay instance
        potd = parse_potd(rss_potd)
        if potd is None:
            return None

        # download tumbnail and high resolution images for the above potd instance
        # exit if either of them fails or is None
        thumbnail_image = await self.download_image(potd.thumbnail_image_url)
        hi_res_image = await self.download_image(potd.high_res_image_url)
        if thumbnail_image is None or hi_res_image is None:
            return None

        # upload thumbnail and high resolution images to the gcs bucket / cdn
        thumbnail_cdn_url = self.upload_image(image=thumbnail_image, is_thumbnail=True)
        hires_cdn_url = self.upload_image(image=hi_res_image, is_thumbnail=False)
        if thumbnail_cdn_url is None or hires_cdn_url is None:
            return None

        # return the above potd instance with thumbnail and hi-res image urls replaced by cdn urls
        return PictureOfTheDay(
            title=potd.title,
            description=potd.description,
            published_date=potd.published_date,
            thumbnail_image_url=HttpUrl(thumbnail_cdn_url),
            high_res_image_url=HttpUrl(hires_cdn_url),
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
        or None.
        """
        if not is_valid_potd_image_url(url):
            return None

        try:
            # set up request headers to only accept image content types
            request_headers = {"accept": "image/jpeg,image/png,image/webp"}
            response: Response = await self.http_client.get(str(url), headers=request_headers)
            response.raise_for_status()

            content = response.content
            content_type = response.headers["content-type"]

            return Image(
                content=content,
                content_type=str(content_type),
            )
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return None

    def upload_image(self, image: Image, is_thumbnail: bool) -> str | None:
        """Upload an image to the bucket."""
        potd_path_and_name = build_potd_path_and_name(image=image, is_thumbnail=is_thumbnail)

        try:
            # return a public cdn url for the image after a successful upload
            return self.gcs_uploader.upload_image(image=image, destination_name=potd_path_and_name)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return None
