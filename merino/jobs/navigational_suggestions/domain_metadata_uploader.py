"""Upload the domain metadata to GCS"""
import datetime
import hashlib
import logging
import time
from urllib.parse import urljoin

from google.cloud.storage import Blob, Client

from merino.jobs.navigational_suggestions.utils import FaviconDownloader, FaviconImage

logger = logging.getLogger(__name__)


class DomainMetadataUploader:
    """Upload the domain metadata to GCS"""

    DESTINATION_FAVICONS_ROOT = "favicons"
    DESTINATION_TOP_PICK_FILE_NAME_SUFFIX = "top_picks.json"

    bucket_name: str
    storage_client: Client
    cdn_hostname: str

    def __init__(
        self,
        destination_gcp_project: str,
        destination_bucket_name: str,
        destination_cdn_hostname: str,
        force_upload: bool,
        favicon_downloader: FaviconDownloader = None,
    ) -> None:
        self.storage_client = Client(destination_gcp_project)
        self.bucket_name = destination_bucket_name
        self.cdn_hostname = destination_cdn_hostname
        self.force_upload = force_upload
        self.favicon_downloader = (
            favicon_downloader if favicon_downloader else FaviconDownloader()
        )

    def upload_top_picks(self, top_picks: str) -> Blob:
        """Upload the top pick contents to gcs."""
        bucket = self.storage_client.bucket(self.bucket_name)
        dst_top_pick_name = self._destination_top_pick_name()
        dst_blob = bucket.blob(dst_top_pick_name)
        dst_blob.upload_from_string(top_picks)
        return dst_blob

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
                favicon_image: FaviconImage = self.favicon_downloader.download_favicon(
                    src_favicon
                )
                dst_favicon_name = self._destination_favicon_name(favicon_image)
                dst_blob = bucket.blob(dst_favicon_name)

                # upload favicon to gcs if force upload is set or if it doesn't exist there and
                # make it publicly accessible
                if self.force_upload or not dst_blob.exists():
                    logger.info(
                        f"Uploading favicon {src_favicon} to blob {dst_favicon_name}"
                    )
                    dst_blob.upload_from_string(
                        favicon_image.content, content_type=favicon_image.content_type
                    )
                    dst_blob.make_public()

                dst_favicon_public_url = self._get_favicon_public_url(
                    dst_blob, dst_favicon_name
                )
                logger.info(f"favicon public url: {dst_favicon_public_url}")
                dst_favicons.append(dst_favicon_public_url)
            except Exception as e:
                logger.info(f"Exception {e} occured while uploading {src_favicon}")
                dst_favicons.append("")

        return dst_favicons

    def _get_favicon_public_url(self, blob: Blob, favicon_name: str) -> str:
        """Get public url for the uploaded favicon"""
        if self.cdn_hostname:
            base_url = (
                f"https://{self.cdn_hostname}"
                if "https" not in self.cdn_hostname
                else self.cdn_hostname
            )
            return urljoin(base_url, favicon_name)
        else:
            return str(blob.public_url)

    def _destination_favicon_name(self, favicon_image: FaviconImage) -> str:
        """Return the name of the favicon to be used for uploading to GCS"""
        content_hex_digest = hashlib.sha256(favicon_image.content).hexdigest()
        content_len = str(len(favicon_image.content))
        extension = ""
        match favicon_image.content_type:
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
                logger.info(f"Couldn't find a match for {favicon_image.content_type}")
                extension = ".oct"

        return f"{self.DESTINATION_FAVICONS_ROOT}/{content_hex_digest}_{content_len}{extension}"
