"""Protocol for Wikimedia Picture of the Day provider backends."""

from typing import Protocol

from pydantic import BaseModel, Field


class Potd(BaseModel):
    """Model for the Wikimedia Picture of the Day."""

    title: str = Field(description="Title of the picture of the day.")
    image_url: str = Field(description="URL of the picture of the day image.")


class WikimediaPotdBackend(Protocol):
    """Protocol for a Wikimedia POTD backend that this provider depends on."""

    async def fetch(self) -> Potd | None:  # pragma: no cover
        """Fetch the current Wikimedia Picture of the Day.

        Returns:
            A Potd instance if data is available, otherwise None.
        """
        ...
