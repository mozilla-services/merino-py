from abc import ABC, abstractmethod

from pydantic import BaseModel


class Image(BaseModel):
    """Data model for Image contents and associated metadata."""

    content: bytes
    content_type: str


class BaseContentUploader(ABC):
    """Abstract class for uploading content to GCS."""

    @abstractmethod
    def upload_content(
        self, content: str, destination_name: str, content_type: str
    ) -> str:
        """Abstract method for uploading content to our GCS Bucket."""
        ...

    @abstractmethod
    def upload_image(
        self,
        image: Image,
        destination_name: str,
    ) -> str:
        """Abstract method for uploading an image to our GCS Bucket."""
        ...
