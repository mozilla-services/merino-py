from abc import ABC, abstractmethod
from typing import Callable

from google.cloud.storage import Blob
from pydantic import BaseModel, Field


class Image(BaseModel):
    """Data model for Image contents and associated metadata."""

    content: bytes
    content_type: str = Field(
        description="Content type of the Image. Can be 'image/png', 'image/jpeg', 'image'"
    )


class BaseContentUploader(ABC):
    """Abstract class for uploading content to GCS."""

    @abstractmethod
    def upload_content(
        self, content: str, destination_name: str, content_type: str = "text/plain"
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
