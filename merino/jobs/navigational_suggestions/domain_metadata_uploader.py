"""Upload the domain metadata to GCS"""
import hashlib
import json
import logging
from datetime import datetime

from google.cloud.storage import Blob, Bucket, Client

from merino.content_handler.models import BaseContentUploader, Image
from merino.jobs.navigational_suggestions.utils import FaviconDownloader

logger = logging.getLogger(__name__)


class DomainMetadataUploader:
    """Upload the domain metadata to GCS"""

    DESTINATION_FAVICONS_ROOT: str = "favicons"
    DESTINATION_TOP_PICK_FILE_NAME: str = "top_picks_latest.json"

    favicon_downloader: FaviconDownloader

    def __init__(
        self,
        force_upload: bool,
        uploader: BaseContentUploader,
        favicon_downloader: FaviconDownloader = FaviconDownloader(),
    ) -> None:
        self.uploader = uploader
        self.force_upload = force_upload
        self.favicon_downloader = favicon_downloader

    def upload_top_picks(self, top_picks: str) -> Blob:
        """Upload the top pick contents to GCS.
        One file is prepended by a timestamp for record keeping,
        the other file is the latest entry from which data is loaded.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        timestamp_file_name = f"{timestamp}_top_picks.json"

        self.uploader.upload_content(top_picks, self.DESTINATION_TOP_PICK_FILE_NAME)
        dated_blob: Blob = self.uploader.upload_content(top_picks, timestamp_file_name)

        return dated_blob

    def get_latest_file_for_diff(
        self,
    ) -> dict[str, list[dict[str, str]]]:
        """Get the most recent top pick file with timestamp so a comparison
        can be made between the previous file and the new file to be written.
        """
        most_recent = self.uploader.get_most_recent_file(
            exclusion=self.DESTINATION_TOP_PICK_FILE_NAME,
            sort_key=lambda blob: blob.name,
        )
        data = most_recent.download_as_text()
        file_contents: dict = json.loads(data)
        logger.info(f"Domain file {most_recent.name} acquired.")
        return file_contents

    def upload_favicons(self, src_favicons: list[str]) -> list[str]:
        """Upload the domain favicons to gcs using their source url and
        return the public urls of the uploaded ones.
        """
        dst_favicons: list = []
        for src_favicon in src_favicons:
            dst_favicon_public_url: str = ""
            favicon_image: Image | None = self.favicon_downloader.download_favicon(
                src_favicon
            )
            if favicon_image:
                try:
                    dst_favicon_name = self.destination_favicon_name(favicon_image)
                    dst_favicon_public_url = self.uploader.upload_image(
                        favicon_image, dst_favicon_name, forced_upload=self.force_upload
                    )
                    logger.info(f"favicon public url: {dst_favicon_public_url}")
                except Exception as e:
                    logger.info(f"Exception {e} occurred while uploading {src_favicon}")

            dst_favicons.append(dst_favicon_public_url)

        return dst_favicons

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
            case _:
                logger.info(f"Couldn't find a match for {favicon_image.content_type}")
                extension = ".oct"

        return f"{self.DESTINATION_FAVICONS_ROOT}/{content_hex_digest}_{content_len}{extension}"
