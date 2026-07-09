"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
import feedparser
from datetime import datetime, timezone
from pydantic import HttpUrl
from feedparser import FeedParserDict
from httpx import AsyncClient, Response

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.providers.rss.wikimedia_potd.backends.utils import (
    RSS_FETCH_REQUEST_HEADERS,
    extract_potd,
    parse_potd,
    build_potd_image_path,
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

    async def upload_picture_of_the_day(self) -> bool:
        """Orchestrates fetching the RSS feed, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        # This is the single error boundary for the upload job: every helper below either
        # returns a value or raises, and any failure is reported to Sentry once here.
        try:
            # fetch the Wikimedia potd rss feed
            rss_potd = await self.fetch_picture_of_the_day_from_feed()

            # parse the feed to extract a PictureOfTheDay instance
            potd = parse_potd(rss_potd)

            # download thumbnail and high resolution images and get the respective cdn urls
            thumbnail_url, hi_res_url = await self.download_and_upload_potd_images(potd)

            potd_to_upload = potd.model_copy(
                update={"thumbnail_image_url": thumbnail_url, "high_res_image_url": hi_res_url}
            )

            self.upload_potd_manifest(potd_to_upload)

            return True
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return False

    async def download_and_upload_potd_images(
        self, potd: PictureOfTheDay
    ) -> tuple[HttpUrl, HttpUrl]:
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            tuple[HttpUrl, HttpUrl]. Raises WikimediaPotdError on failure.
        """
        # download thumbnail and high resolution images for the above potd instance
        thumbnail_image = await self.download_potd_image(potd.thumbnail_image_url)
        hi_res_image = await self.download_potd_image(potd.high_res_image_url)

        # upload thumbnail and high resolution images to the gcs bucket / cdn
        thumbnail_cdn_url = self.upload_potd_image(image=thumbnail_image, is_thumbnail=True)
        hires_cdn_url = self.upload_potd_image(image=hi_res_image, is_thumbnail=False)

        return (HttpUrl(thumbnail_cdn_url), HttpUrl(hires_cdn_url))

    async def fetch_picture_of_the_day_from_feed(self) -> FeedParserDict:
        """Fetch Wikimedia Commons picture of the day RSS feed.

        Returns:
            A FeedParseDict object containing xml. Raises WikimediaPotdError on failure.
        """
        feed: Response = await self.http_client.get(
            self.feed_url, headers=RSS_FETCH_REQUEST_HEADERS
        )

        feed.raise_for_status()

        if not feed.content:
            raise WikimediaPotdError("Wikimedia POTD feed returned empty content")

        parsed_feed: FeedParserDict = feedparser.parse(feed.text)

        return extract_potd(parsed_feed)

    async def download_potd_image(self, url: HttpUrl) -> Image:
        """Download the image using the image URL.

        Returns:
            An Image object containing the binary content and content type.
            Raises WikimediaPotdError on failure.
        """
        if not is_valid_potd_image_url(url):
            raise WikimediaPotdError(f"Invalid Wikimedia POTD image url: {url}")

        # set up request headers to only accept image content types
        request_headers = {
            **RSS_FETCH_REQUEST_HEADERS,
            "accept": "image/jpeg,image/png,image/webp",
        }
        response: Response = await self.http_client.get(str(url), headers=request_headers)
        response.raise_for_status()

        content = response.content
        content_type = response.headers["content-type"]

        return Image(
            content=content,
            content_type=str(content_type),
        )

    def upload_potd_image(self, image: Image, is_thumbnail: bool) -> str:
        """Upload an image to the bucket.

        Returns:
            Public gcs bucket cdn url (str) of the uploaded image.
            Raises WikimediaPotdError if the image fails to upload.
        """
        potd_image_path = build_potd_image_path(image=image, is_thumbnail=is_thumbnail)

        # return a public cdn url for the image after a successful upload
        public_url = self.gcs_uploader.upload_image(image=image, destination_name=potd_image_path)

        # GcsUploader.upload_content swallows storage errors and returns a public url regardless,
        # so confirm the object actually landed in the bucket and fail loudly otherwise.
        if self.gcs_uploader.get_file_by_name(potd_image_path) is None:
            raise WikimediaPotdError(f"Failed to upload POTD image: {potd_image_path}")

        return public_url

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> None:
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Raises WikimediaPotdError if the manifest fails to upload.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # manifest json is just the PictureOfTheDay model in json format
        manifest_json = potd.model_dump_json()
        destination_name = f"rss/wikimedia_potd/POTD_{today}.json"

        self.gcs_uploader.upload_content(
            content=manifest_json,
            destination_name=destination_name,
            content_type="application/json",
            forced_upload=True,
        )

        # GcsUploader.upload_content swallows storage errors, so confirm the object actually
        # landed in the bucket and fail loudly otherwise.
        if self.gcs_uploader.get_file_by_name(destination_name) is None:
            raise WikimediaPotdError(f"Failed to upload POTD manifest: {destination_name}")

    def fetch_potd_from_gcs_bucket(self) -> PictureOfTheDay | None:
        """Fetch the PictureOfTheDay object from the gcs bucket.

        Returns:
            A PictureOfTheDay object if available, otherwise None.
        """
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
