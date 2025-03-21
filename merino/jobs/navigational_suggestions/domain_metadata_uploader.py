"""Upload the domain metadata to GCS"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import List

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
        logger.info(f"Domain file {most_recent.name} acquired.")
        return file_contents

    def upload_favicons(self, src_favicons: list[str]) -> list[str]:
        """Upload the domain favicons to gcs using their source url and
        return the public urls of the uploaded ones.
        """
        return asyncio.run(self.upload_favicons_async(src_favicons))

    async def upload_favicons_async(self, src_favicons: List[str]) -> List[str]:
        """Upload the domain favicons to GCS asynchronously"""
        # Filter out URLs that are already from our CDN
        cdn_urls = []
        urls_to_download = []
        indices = []

        for i, url in enumerate(src_favicons):
            if url and url.startswith(f"https://{self.uploader.cdn_hostname}"):
                cdn_urls.append((i, url))
            else:
                urls_to_download.append(url)
                indices.append(i)

        # Download favicons in parallel
        favicon_images = await self.async_favicon_downloader.download_multiple_favicons(
            urls_to_download
        )

        # Process results and upload to GCS
        results = [""] * len(src_favicons)  # Initialize with empty strings

        # Add CDN URLs directly
        for idx, url in cdn_urls:
            results[idx] = url

        # Process downloaded images
        for local_idx, (orig_idx, favicon_image) in enumerate(zip(indices, favicon_images)):
            if favicon_image:
                try:
                    dst_favicon_name = self.destination_favicon_name(favicon_image)
                    dst_favicon_public_url = self.uploader.upload_image(
                        favicon_image, dst_favicon_name, forced_upload=self.force_upload
                    )
                    results[orig_idx] = dst_favicon_public_url
                    logger.info(f"Favicon {orig_idx} uploaded: {dst_favicon_public_url}")
                except Exception as e:
                    logger.info(f"Exception {e} occurred while uploading favicon {orig_idx}")

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
                logger.info(f"Couldn't find a match for {favicon_image.content_type}")
                extension = ".oct"

        return f"{self.DESTINATION_FAVICONS_ROOT}/{content_hex_digest}_{content_len}{extension}"
