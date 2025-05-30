"""Upload the domain metadata to GCS"""

import hashlib
import json
import logging
from datetime import datetime

from google.cloud.storage import Blob

from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.jobs.navigational_suggestions.utils import AsyncFaviconDownloader

logger = logging.getLogger(__name__)


class DomainMetadataUploader:
    """Upload the domain metadata to GCS"""

    DESTINATION_FAVICONS_ROOT: str = "favicons"
    DESTINATION_TOP_PICK_FILE_NAME: str = "top_picks_latest.json"

    async_favicon_downloader: AsyncFaviconDownloader

    def __init__(
        self,
        force_upload: bool,
        uploader: GcsUploader,
        async_favicon_downloader: AsyncFaviconDownloader,
    ) -> None:
        self.uploader = uploader
        self.force_upload = force_upload
        self.async_favicon_downloader = async_favicon_downloader

    def upload_top_picks(self, top_picks: str) -> Blob:
        """Upload the top pick contents to GCS.
        One file is prepended by a timestamp for record keeping,
        the other file is the latest entry from which data is loaded.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        timestamp_file_name = f"{timestamp}_top_picks.json"

        self.uploader.upload_content(
            top_picks, self.DESTINATION_TOP_PICK_FILE_NAME, forced_upload=True
        )
        dated_blob: Blob = self.uploader.upload_content(top_picks, timestamp_file_name)

        return dated_blob

    def get_latest_file_for_diff(
        self,
    ) -> dict[str, list[dict[str, str]]] | None:
        """Get the most recent top pick file with timestamp so a comparison
        can be made between the previous file and the new file to be written.
        """
        most_recent = self.uploader.get_most_recent_file(
            exclusion=self.DESTINATION_TOP_PICK_FILE_NAME,
            sort_key=lambda blob: blob.name,
        )
        # early exit if no file is returned from the uploader
        if most_recent is None:
            return None

        data = most_recent.download_as_text()
        file_contents: dict = json.loads(data)
        return file_contents

    async def upload_favicon(self, favicon_url: str) -> str:
        """Upload a single favicon to GCS and return its public URL.

        Args:
            favicon_url: URL of the favicon to upload

        Returns:
            Public URL of the uploaded favicon or empty string if upload failed
        """
        if not favicon_url:
            return ""

        # If URL is already from our CDN, return it directly
        if favicon_url and favicon_url.startswith(f"https://{self.uploader.cdn_hostname}"):
            return favicon_url

        favicon_image = await self.async_favicon_downloader.download_favicon(favicon_url)

        # Process and upload the favicon
        if favicon_image:
            try:
                dst_favicon_name = self.destination_favicon_name(favicon_image)
                dst_favicon_public_url = self.uploader.upload_image(
                    favicon_image, dst_favicon_name, forced_upload=self.force_upload
                )
                return dst_favicon_public_url
            except Exception as e:
                logger.debug(f"Failed to upload favicon: {e}")

        return ""

    def upload_image(
        self, favicon_image: Image, dst_favicon_name: str, forced_upload: bool
    ) -> str:
        """Upload an already downloaded favicon image to GCS and return its public URL.

        Args:
            favicon_image: The Image object to upload
            dst_favicon_name: The destination filename to use
            forced_upload: Whether to force upload even if file exists

        Returns:
            Public URL of the uploaded favicon
        """
        return self.uploader.upload_image(
            favicon_image, dst_favicon_name, forced_upload=forced_upload
        )

    async def upload_favicons(self, src_favicons: list[str]) -> list[str]:
        """Upload multiple domain favicons to GCS using their source URLs.

        For backward compatibility with partner favicons.

        Args:
            src_favicons: List of favicon URLs to upload

        Returns:
            List of public URLs of the uploaded favicons
        """
        results = []
        for favicon_url in src_favicons:
            result = await self.upload_favicon(favicon_url)
            # Ensure we always return a string, even for None or failed uploads
            results.append(result if isinstance(result, str) else "")
        return results

    def destination_favicon_name(self, favicon_image: Image) -> str:
        """Return the name of the favicon to be used for uploading to GCS"""
        content_hex_digest: str = hashlib.sha256(favicon_image.content).hexdigest()
        content_len: str = str(len(favicon_image.content))
        extension: str = ""
        match favicon_image.content_type:
            case "image/jpeg" | "image/jpg":
                extension = ".jpeg"
            case "image/png":
                extension = ".png"
            case "image/svg+xml":
                extension = ".svg"
            case "image/x-icon":
                extension = ".ico"
            case "image/webp":
                extension = ".webp"
            case "image/gif":
                extension = ".gif"
            case _:
                extension = ".oct"

        return f"{self.DESTINATION_FAVICONS_ROOT}/{content_hex_digest}_{content_len}{extension}"
