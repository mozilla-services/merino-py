"""Base Image and Content Uploader models"""

from abc import ABC, abstractmethod
from io import BytesIO
from typing import Callable

from google.cloud.storage import Blob
from PIL import Image as PILImage
from pydantic import BaseModel, Field


class Image(BaseModel):
    """Data model for Image contents and associated metadata."""

    content: bytes
    content_type: str = Field(
        description="Content type of the Image. Can be 'image/png', 'image/jpeg', 'image'"
    )

    def open(self) -> PILImage.Image:
        """Open and return an PIL Image object"""
        with PILImage.open(BytesIO(self.content)) as image:
            return image

    def get_dimensions(self) -> tuple[int, int]:
        """Get image dimensions and properly close the file"""
        with PILImage.open(BytesIO(self.content)) as img:
            return img.size


class BaseContentUploader(ABC):
    """Abstract class for uploading content to GCS."""

    @abstractmethod
    def upload_content(
        self,
        content: bytes | str,
        destination_name: str,
        content_type: str = "text/plain",
        forced_upload: bool = False,
    ) -> Blob:
        """Abstract method for uploading content to our GCS Bucket."""
        ...

    @abstractmethod
    def upload_image(
        self,
        image: Image,
        destination_name: str,
        forced_upload=None,
    ) -> str:
        """Abstract method for uploading an image to our GCS Bucket."""
        ...

    @abstractmethod
    def get_most_recent_file(
        self, match: str, sort_key: Callable, exclusion: str | None
    ) -> Blob | None:
        """Abstract method for getting the most recent file from the GCS bucket."""
        ...
