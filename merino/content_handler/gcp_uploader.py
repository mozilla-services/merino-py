"""Uploads Content to GCS"""
import logging
from typing import Callable
from urllib.parse import urljoin

from google.cloud.storage import Blob, Bucket, Client

from merino.content_handler.models import Image

logger = logging.getLogger(__name__)


class GcsUploader:
    """Class that includes shared logic to upload an image to GCP."""

    storage_client: Client
    bucket_name: str
    cdn_hostname: str

    def __init__(
        self,
        destination_gcp_project: str,
        destination_bucket_name: str,
        destination_cdn_hostname: str,
    ) -> None:
        self.storage_client = Client(destination_gcp_project)
        self.bucket_name = destination_bucket_name
        self.cdn_hostname = destination_cdn_hostname

    def upload_image(
        self, image: Image, destination_name: str, forced_upload: bool = False
    ) -> str:
        """Upload an Image to our GCS Bucket and return the public URL where it is hosted."""
        image_blob: Blob = self.upload_content(
            image.content, destination_name, image.content_type, forced_upload
        )
        image_public_url = self._get_public_url(image_blob, destination_name)

        logger.info(f"Content public url: {image_public_url}")

        return image_public_url

    def upload_content(
        self,
        content: bytes,
        destination_name: str,
        content_type: str = "text/plain",
        forced_upload: bool = False,
    ) -> Blob:
        """Upload the content then return the blob."""
        bucket: Bucket = self.storage_client.bucket(self.bucket_name)
        destination_blob = bucket.blob(destination_name)

        try:
            if forced_upload or not destination_blob.exists():
                logger.info(f"Uploading blob: {destination_blob}")
                destination_blob.upload_from_string(
                    content,
                    content_type=content_type,
                )
                destination_blob.make_public()

        except Exception as e:
            logger.error(f"Exception {e} occurred while uploading {destination_name}")

        return destination_blob

    def get_most_recent_file(self, exclusion: str, sort_key: Callable) -> Blob | None:
        bucket: Bucket = self.storage_client.get_bucket(self.bucket_name)
        blobs = [
            blob
            for blob in bucket.list_blobs(delimiter="/", match_glob="*.json")
            if blob.name != exclusion
        ]

        if not blobs:
            return None
        # return the most recent file. this sorts in ascending order, we are getting the last file.
        most_recent = sorted(blobs, key=sort_key)[-1]
        return most_recent

    def _get_public_url(self, blob: Blob, favicon_name: str) -> str:
        """Get public url for some content"""
        if self.cdn_hostname:
            base_url = (
                f"https://{self.cdn_hostname}"
                if "https" not in self.cdn_hostname
                else self.cdn_hostname
            )
            return urljoin(base_url, favicon_name)
        else:
            return str(blob.public_url)
