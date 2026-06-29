"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
import feedparser
from datetime import datetime
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


class WikimediaPictureOfTheDayBackend:
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

    async def orchestrate_picture_of_the_day_upload(self) -> bool:
        """Orchestrates fetching the RSS feed, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        try:
            # fetch the Wikimedia potd rss feed
            rss_potd = await self.fetch_picture_of_the_day_from_feed()
            if rss_potd is None:
                return False

            # parse the feed to extract a PictureOfTheDay instance
            # this method will return None if the potd feed entry is malformed
            potd = parse_potd(rss_potd)
            if potd is None:
                return False

            # download thumbnail and high resolution images
            # and get the respective cdn urls, None if failed
            image_urls = await self.download_and_upload_potd_images(potd)
            if image_urls is None:
                return False

            thumbail_url, hi_res_url = image_urls

            potd_to_upload = potd.model_copy(
                update={"thumbnail_image_url": thumbail_url, "high_res_image_url": hi_res_url}
            )

            return self.upload_potd_manifest(potd_to_upload)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return False

    async def download_and_upload_potd_images(
        self, potd: PictureOfTheDay
    ) -> tuple[HttpUrl, HttpUrl] | None:
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            Bool. True if success, False if failure.
        """
        # download thumbnail and high resolution images for the above potd instance
        # exit if either of them fails or is None
        thumbnail_image = await self.download_potd_image(potd.thumbnail_image_url)
        hi_res_image = await self.download_potd_image(potd.high_res_image_url)
        if thumbnail_image is None or hi_res_image is None:
            return None

        # upload thumbnail and high resolution images to the gcs bucket / cdn
        # exit if either of them fails or is None
        thumbnail_cdn_url = self.upload_potd_image(image=thumbnail_image, is_thumbnail=True)
        hires_cdn_url = self.upload_potd_image(image=hi_res_image, is_thumbnail=False)
        if thumbnail_cdn_url is None or hires_cdn_url is None:
            return None

        # TODO
        return (HttpUrl(thumbnail_cdn_url), HttpUrl(hires_cdn_url))

    async def fetch_picture_of_the_day_from_feed(self) -> FeedParserDict | None:
        """Fetch Wikimedia Commons picture of the day RSS feed.

        Returns:
            A FeedParseDict object containing xml or None.
        """
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

    async def download_potd_image(self, url: HttpUrl) -> Image | None:
        """Download the image using the image URL.

        Returns:
            An Image object containing the binary content and content type, or None.
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

    def upload_potd_image(self, image: Image, is_thumbnail: bool) -> str | None:
        """Upload an image to the bucket.

        Returns:
            Public gcs bucket cdn url (str) of the uploaded image, or None.
        """
        potd_path_and_name = build_potd_path_and_name(image=image, is_thumbnail=is_thumbnail)

        try:
            # return a public cdn url for the image after a successful upload
            return self.gcs_uploader.upload_image(image=image, destination_name=potd_path_and_name)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return None

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> bool:
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Returns:
            Bool. True if success, False if failure
        """
        try:
            today = datetime.today().strftime("%Y-%m-%d")

            # manifest json is just the PictureOfTheDay model in json format
            manifest_json = potd.model_dump_json()

            self.gcs_uploader.upload_content(
                content=manifest_json,
                destination_name=f"rss/wikimedia_potd/POTD_{today}.json",
                content_type="application/json",
                forced_upload=True,
            )

            return True
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return False

    def fetch_potd_from_gcs_bucket(self) -> PictureOfTheDay | None:
        """Fetch the PictureOfTheDay object from the gcs bucket.

        Returns:
            A PictureOfTheDay object if available, otherwise None.
        """
        try:
            today = datetime.today().strftime("%Y-%m-%d")
            blob = self.gcs_uploader.get_file_by_name(f"rss/wikimedia_potd/POTD_{today}.json")

            if blob:
                potd_json = blob.download_as_text()
                return PictureOfTheDay.model_validate_json(potd_json)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)

        return None

    async def shutdown(self) -> None:
        """Shutdown the backend.

        Returns:
            None.
        """
        await self.http_client.aclose()
