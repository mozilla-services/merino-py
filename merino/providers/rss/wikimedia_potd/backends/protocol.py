"""Protocol for Wikimedia Picture of the Day provider backends."""

from typing import Protocol
from pydantic import BaseModel, Field, HttpUrl
from feedparser import FeedParserDict
from merino.utils.gcs.models import Image


class PictureOfTheDay(BaseModel):
    """Model for the Wikimedia Picture of the Day."""

    title: str = Field(description="Title of the picture of the day.")
    thumbnail_image_url: HttpUrl = Field(
        description="Thumbnail URL of the picture of the day image."
    )
    high_res_image_url: HttpUrl = Field(
        description="High resolution URL of the picture of the day image."
    )
    published_date: str = Field(description="Date when the image was published.")
    description: str = Field(description="Description of the image.")


class WikimediaPictureOfTheDayBackend(Protocol):
    """Protocol for a Wikimedia POTD backend that this provider depends on."""

    async def orchestrate_picture_of_the_day_upload(self) -> bool:  # pragma: no cover
        """Orchestrates fetching the RSS feed, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        ...

    async def download_and_upload_potd_images(
        self, potd: PictureOfTheDay
    ) -> tuple[HttpUrl, HttpUrl] | None:  # pragma: no cover
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            tuple[HttpUrl, HttpUrl] | None.
        """
        ...

    async def fetch_picture_of_the_day_from_feed(
        self,
    ) -> FeedParserDict | None:  # pragma: no cover
        """Fetch Wikimedia Commons picture of the day RSS feed.

        Returns:
            A FeedParseDict object containing xml or None.
        """
        ...

    async def download_potd_image(self, url: HttpUrl) -> Image | None:  # pragma: no cover
        """Download the image using the image URL.

        Returns:
            An Image object containing the binary content and content type, or None.
        """
        ...

    def upload_potd_image(
        self, image: Image, is_thumbnail: bool
    ) -> str | None:  # pragma: no cover
        """Upload an image to the bucket.

        Returns:
            Public gcs bucket cdn url (str) of the uploaded image, or None.
        """
        ...

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> bool:  # pragma: no cover
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Returns:
            Bool. True if success, False if failure
        """
        ...

    def fetch_potd_from_gcs_bucket(self) -> PictureOfTheDay | None:  # pragma: no cover
        """Fetch the PictureOfTheDay object from the gcs bucket.

        Returns:
            A PictureOfTheDay object if available, otherwise None.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shutdown the backend.

        Returns:
            None.
        """
