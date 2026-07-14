"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
from datetime import datetime, timezone
from pydantic import HttpUrl
from httpx import AsyncClient, Response

from merino.configs import settings
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.providers.rss.wikimedia_potd.backends.utils import (
    WIKIMEDIA_REQUEST_HEADERS,
    parse_potd,
    build_potd_bucket_directory_path,
    is_valid_potd_image_url,
)
import sentry_sdk

logger = logging.getLogger(__name__)


class WikimediaPictureOfTheDayBackend:
    """Backend for fetching the Wikimedia Picture of the Day from the Featured API."""

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
        """Initialize the backend with the Featured API base url."""
        self.feed_url = feed_url
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.gcs_uploader = gcs_uploader
        self.cache_control = settings.rss_providers.wikimedia_potd.cache_control

    async def upload_picture_of_the_day(self) -> bool:
        """Orchestrates fetching the Featured API, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        # This is the single error boundary for the upload job: every helper below either
        # returns a value or raises, and any failure is reported to Sentry once here.
        try:
            # fetch today's Wikimedia Featured API response
            data = await self.fetch_picture_of_the_day()

            # parse the response to extract a PictureOfTheDay instance
            potd = parse_potd(data)

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

    async def fetch_picture_of_the_day(self) -> dict:
        """Fetch the Wikimedia Featured API picture of the day for today.

        Returns:
            The parsed JSON response as a dict. Raises WikimediaPotdError on failure.
        """
        # setting the format to YYYY/MM/DD which is accepted as the url param
        today = datetime.now(timezone.utc).strftime("%Y/%m/%d")

        # the Featured API expects the date in the url path: .../en/featured/{yyyy}/{mm}/{dd}
        url = f"{self.feed_url}/{today}"

        response: Response = await self.http_client.get(url, headers=WIKIMEDIA_REQUEST_HEADERS)

        response.raise_for_status()

        if not response.content:
            raise WikimediaPotdError("Wikimedia POTD featured api returned empty content")

        try:
            data: dict = response.json()
        except ValueError as ex:
            raise WikimediaPotdError("Wikimedia POTD featured api returned invalid JSON") from ex

        return data

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
            **WIKIMEDIA_REQUEST_HEADERS,
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
        # name the image file "thumbnail" or "hi_res" depending on the image variant
        suffix = "thumbnail" if is_thumbnail else "hi_res"

        # extract image extension since the image.content_type has the format image/jpeg
        extension = image.content_type.split("/")[-1]

        potd_image_path = f"{build_potd_bucket_directory_path()}{suffix}.{extension}"

        # return a public cdn url for the image after a successful upload
        public_url = self.gcs_uploader.upload_image(
            image=image, destination_name=potd_image_path, cache_control=self.cache_control
        )

        # GcsUploader.upload_content swallows storage errors and returns a public url regardless,
        # so confirm the object actually landed in the bucket and fail loudly otherwise.
        if self.gcs_uploader.get_file_by_name(potd_image_path) is None:
            raise WikimediaPotdError(f"Failed to upload POTD image: {potd_image_path}")

        return public_url

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> None:
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Raises WikimediaPotdError if the manifest fails to upload.
        """
        # manifest json is just the PictureOfTheDay model in json format
        manifest_json = potd.model_dump_json()
        destination_name = f"{build_potd_bucket_directory_path()}manifest.json"

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
            blob = self.gcs_uploader.get_file_by_name(
                f"{build_potd_bucket_directory_path()}manifest.json"
            )

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
