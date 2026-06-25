"""Protocol for Wikimedia Picture of the Day provider backends."""

from typing import Protocol
from pydantic import BaseModel, Field, HttpUrl


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

    async def download_and_upload_potd_images(self) -> bool:  # pragma: no cover
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            Bool. True if success, False if failure.
        """
        ...

    def build_and_upload_potd(self, potd: PictureOfTheDay) -> bool:
        """Build a PictureOfTheDay object and upload it to the gcs bucket.

        Returns:
            Bool. True if success, False if failure
        """
        ...

    def fetch_potd_from_gcs_bucket(self) -> PictureOfTheDay | None:  # pragma: no cover
        """Fetch the Wikimedia picture of the day from the gcs bucket.

        Returns:
            A PictureOfTheDay object if available, otherwise None.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shutdown the backend.

        Returns:
            None.
        """
