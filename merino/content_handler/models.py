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

    @staticmethod
    def open(bytes_io: BytesIO) -> PILImage:
        """Open and return an PIL Image object"""
        return PILImage.open(bytes_io)


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
    def get_most_recent_file(self, exclusion: str, sort_key: Callable) -> Blob | None:
        """Abstract method for getting the most recent file from the GCS bucket."""
        ...
