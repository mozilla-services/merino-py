"""Upload the domain metadata to GCS"""
import datetime
import hashlib
import logging
import time

import requests
from google.cloud.storage import Client

logger = logging.getLogger(__name__)


class DomainMetadataUploader:
    """Upload the domain metadata to GCS"""

    FIREFOX_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.3; rv:111.0) Gecko/20100101 "
        "Firefox/111.0"
    )
    DESTINATION_FAVICONS_ROOT = "favicons"
    DESTINATION_TOP_PICK_FILE_NAME_SUFFIX = "top_picks.json"

    bucket_name: str
    storage_client: Client

    def __init__(
        self, destination_gcp_project: str, destination_bucket_name: str
    ) -> None:
        self.storage_client = Client(destination_gcp_project)
        self.bucket_name = destination_bucket_name

    def upload_top_picks(self, top_picks: str) -> None:
        """Upload the top pick contents to gcs."""
        bucket = self.storage_client.bucket(self.bucket_name)
        dst_top_pick_name = self._destination_top_pick_name()
        dst_blob = bucket.blob(dst_top_pick_name)
        dst_blob.upload_from_string(top_picks)

    def _destination_top_pick_name(self) -> str:
        """Return the name of the top pick file to be used for uploading to GCS"""
        current = datetime.datetime.now()
        return (
            str(time.mktime(current.timetuple()) * 1000)
            + "_"
            + self.DESTINATION_TOP_PICK_FILE_NAME_SUFFIX
        )

    def upload_favicons(self, src_favicons: list[str]) -> list[str]:
        """Upload the domain favicons to gcs using their source url and
        return the public urls of the uploaded ones.
        """
        dst_favicons = []
        bucket = self.storage_client.bucket(self.bucket_name)
        for src_favicon in src_favicons:
            try:
                content, content_type = self._download_favicon(src_favicon)
                dst_favicon_name = self._destination_favicon_name(content, content_type)
                dst_blob = bucket.blob(dst_favicon_name)

                # upload favicon to gcs if it doesn't already exist there an
                # make it publicly accessible
                if not dst_blob.exists():
                    logger.info(f"blob {dst_favicon_name} doesn't exist. creating it..")
                    dst_blob.upload_from_string(content, content_type=content_type)
                    dst_blob.make_public()

                dst_favicons.append(dst_blob.public_url)
            except Exception as e:
                logger.info(f"Exception {e} occured while uploading {src_favicon}")
                dst_favicons.append("")

        return dst_favicons

    def _download_favicon(self, favicon: str) -> tuple[bytes, str]:
        """Download favicon image from a given url"""
        response = requests.get(
            favicon, headers={"User-agent": self.FIREFOX_UA}, timeout=60
        )
        return response.content, response.headers["Content-Type"]

    def _destination_favicon_name(self, content: bytes, content_type: str) -> str:
        """Return the name of the favicon to be used for uploading to GCS"""
        hex_digest = hashlib.sha256(content).hexdigest()
        extension = ""
        match content_type:
            case "image/apng":
                extension = ".apng"
            case "image/avif":
                extension = ".avif"
            case "image/gif":
                extension = ".gif"
            case "image/jpeg" | "image/jpg":
                extension = ".jpeg"
            case "image/png":
                extension = ".png"
            case "image/svg+xml":
                extension = ".svg"
            case "image/webp":
                extension = ".webp"
            case "image/bmp":
                extension = ".bmp"
            case "image/x-icon":
                extension = ".ico"
            case "image/tiff":
                extension = ".tiff"
            case _:
                logger.info(f"Couldn't find a match for {content_type}")
                extension = ".oct"

        return f"{self.DESTINATION_FAVICONS_ROOT}/{hex_digest}_{str(len(content))}{extension}"
