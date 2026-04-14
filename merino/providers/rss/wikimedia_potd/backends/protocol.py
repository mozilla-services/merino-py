"""Protocol for Wikimedia Picture of the Day provider backends."""

from typing import Protocol
from pydantic import BaseModel, Field


class PictureOfTheDay(BaseModel):
    """Model for the Wikimedia Picture of the Day."""

    title: str = Field(description="Title of the picture of the day.")
    thumbnail_image_url: str = Field(description="Thumbnail URL of the picture of the day image.")
    high_res_image_url: str = Field(
        description="High resolution URL of the picture of the day image."
    )
    published_date: str = Field(description="Date when the image was published.")


class WikimediaPictureOfTheDayBackend(Protocol):
    """Protocol for a Wikimedia POTD backend that this provider depends on."""

    async def get_picture_of_the_day(self) -> PictureOfTheDay | None:  # pragma: no cover
        """Fetch the current Wikimedia Picture of the Day.

        Returns:
            A Potd instance if data is available, otherwise None.
        """
        ...
