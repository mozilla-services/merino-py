"""Protocol for Wikimedia Picture of the Day provider backends."""

from typing import Protocol
from pydantic import BaseModel, Field, HttpUrl
from merino.exceptions import BackendError
from merino.utils.gcs.models import Image


class WikimediaPotdError(BackendError):
    """Error raised by the Wikimedia POTD backend when the picture of the day cannot be produced."""


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
    artist: str = Field(default="", description="Name of the image's artist.")
    file_page: HttpUrl | None = Field(default=None, description="Commons file page URL.")
    license_label: str = Field(default="", description="License type, e.g. 'CC BY-SA 4.0'.")
    license_link: HttpUrl | None = Field(default=None, description="License URL.")


class WikimediaPictureOfTheDayBackend(Protocol):
    """Protocol for a Wikimedia POTD backend that this provider depends on."""

    async def upload_picture_of_the_day(self) -> bool:  # pragma: no cover
        """Orchestrates fetching the Featured API, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        ...

    async def download_and_upload_potd_images(
        self, potd: PictureOfTheDay
    ) -> tuple[HttpUrl, HttpUrl]:  # pragma: no cover
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            tuple[HttpUrl, HttpUrl]. Raises WikimediaPotdError on failure.
        """
        ...

    async def fetch_picture_of_the_day(
        self,
    ) -> dict:  # pragma: no cover
        """Fetch the Wikimedia Featured API picture of the day for today.

        Returns:
            The parsed JSON response as a dict. Raises WikimediaPotdError on failure.
        """
        ...

    async def download_potd_image(self, url: HttpUrl) -> Image:  # pragma: no cover
        """Download the image using the image URL.

        Returns:
            An Image object containing the binary content and content type.
            Raises WikimediaPotdError on failure.
        """
        ...

    def upload_potd_image(self, image: Image, is_thumbnail: bool) -> str:  # pragma: no cover
        """Upload an image to the bucket.

        Returns:
            Public gcs bucket cdn url (str) of the uploaded image.
            Raises WikimediaPotdError on failure.
        """
        ...

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> None:  # pragma: no cover
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Raises WikimediaPotdError on failure.
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
