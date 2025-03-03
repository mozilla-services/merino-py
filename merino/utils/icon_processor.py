"""Icon processor for handling favicon downloads and uploads to GCS"""

import hashlib
import logging
from typing import Dict, Optional

from merino.configs import settings
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.utils.http_client import create_http_client

logger = logging.getLogger(__name__)


class IconProcessor:
    """Processes external favicon URLs to host them in GCS"""

    uploader: GcsUploader
    content_hash_cache: Dict[str, str]

    def __init__(self, gcs_project: str, gcs_bucket: str) -> None:
        """Initialize the icon processor."""
        self.uploader = GcsUploader(gcs_project, gcs_bucket, "")

        # Content hash cache: {content_hash: gcs_url}
        self.content_hash_cache = {}

    async def process_icon_url(self, url: str) -> str:
        """Process an external icon URL and return a GCS-hosted URL."""
        # Skip URLs that are already from our CDN
        cdn_hostname = self.uploader.cdn_hostname
        if cdn_hostname and url.startswith(f"https://{cdn_hostname}"):
            return url

        try:
            # Download favicon
            favicon_image = await self._download_favicon(url)
            if not favicon_image:
                logger.info(f"Failed to download favicon from {url}")
                return url

            # Check if the image is valid
            if not self._is_valid_image(favicon_image):
                logger.info(f"Invalid image from {url}")
                return url

            # Generate content hash
            content_hash = hashlib.sha256(favicon_image.content).hexdigest()

            # Check content hash cache - this avoids re-uploading identical content
            if content_hash in self.content_hash_cache:
                return self.content_hash_cache[content_hash]

            # Generate destination path based on content hash
            destination = self._get_destination_path(favicon_image, content_hash)

            # GcsUploader already checks if the file exists before uploading
            gcs_url = self.uploader.upload_image(favicon_image, destination, forced_upload=False)

            # Cache the result
            self.content_hash_cache[content_hash] = gcs_url

            return gcs_url

        except Exception as e:
            logger.warning(f"Error processing icon {url}: {e}")
            return url

    async def _download_favicon(self, url: str) -> Optional[Image]:
        """Download the favicon from the given URL.

        Args:
            url: The favicon URL

        Returns:
            Image: The favicon image if download was successful, None otherwise
        """
        try:
            headers = {"User-Agent": "Merino"}

            async with create_http_client(
                request_timeout=settings.icon.http_timeout, max_connections=1
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return Image(
                    content=response.content,
                    content_type=str(response.headers.get("Content-Type", "image/unknown")),
                )
        except Exception as e:
            logger.info(f"Exception {e} while downloading favicon {url}")
            return None

    def _get_destination_path(self, favicon_image: Image, content_hash: str) -> str:
        """Generate GCS path based on content hash."""
        content_len = len(favicon_image.content)

        # Determine file extension from content type
        extension = ""
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
            case "image/bmp":
                extension = ".bmp"
            case "image/tiff":
                extension = ".tiff"
            case content_type if content_type.startswith("image/"):
                # Extract extension from content type
                ext = content_type.split("/")[-1]
                if ext and ext != "unknown":
                    extension = f".{ext}"
                else:
                    extension = ".png"
            case _:
                # Unknown content type, try to detect from content
                try:
                    with favicon_image.open() as img:
                        format = img.format.lower() if img.format else "png"
                        extension = f".{format}"
                        # Update content_type based on detected format for consistency
                        if format == "jpeg":
                            favicon_image.content_type = "image/jpeg"
                        elif format in ["png", "svg", "webp", "gif", "bmp", "tiff"]:
                            favicon_image.content_type = f"image/{format}"
                        elif format == "ico":
                            favicon_image.content_type = "image/x-icon"
                except Exception as e:
                    logger.info(f"Exception detecting image type: {e}")
                    extension = ".png"  # Default to png
                    favicon_image.content_type = "image/png"

        favicon_root = settings.icon.favicons_root

        return f"{favicon_root}/{content_hash}_{content_len}{extension}"

    def _is_valid_image(self, favicon_image: Image) -> bool:
        """Check if the image is valid."""
        # Check content type
        if "image/" not in favicon_image.content_type:
            return False

        # Check size (avoid empty or extremely large images)
        content_size = len(favicon_image.content)
        max_size = settings.icon.max_size

        if content_size < 10 or content_size > max_size:
            return False

        return True
