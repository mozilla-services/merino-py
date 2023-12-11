"""Upload the domain metadata to GCS"""
import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from google.cloud.storage import Blob, Bucket, Client

from merino.jobs.navigational_suggestions.utils import FaviconDownloader, FaviconImage

logger = logging.getLogger(__name__)


class DomainMetadataUploader:
    """Upload the domain metadata to GCS"""

    DESTINATION_FAVICONS_ROOT: str = "favicons"
    DESTINATION_TOP_PICK_FILE_NAME: str = "top_picks_latest.json"

    bucket_name: str
    storage_client: Client
    cdn_hostname: str
    favicon_downloader: FaviconDownloader

    def __init__(
        self,
        destination_gcp_project: str,
        destination_bucket_name: str,
        destination_cdn_hostname: str,
        force_upload: bool,
        favicon_downloader: FaviconDownloader = FaviconDownloader(),
    ) -> None:
        self.storage_client = Client(destination_gcp_project)
        self.bucket_name = destination_bucket_name
        self.cdn_hostname = destination_cdn_hostname
        self.force_upload = force_upload
        self.favicon_downloader = favicon_downloader

    def upload_top_picks(self, top_picks: str) -> Blob:
        """Upload the top pick contents to GCS.
        One file is prepended by a timestamp for record keeping,
        the other file is the latest entry from which data is loaded.
        """
        bucket = self.storage_client.bucket(self.bucket_name)
        dst_top_pick_name = DomainMetadataUploader._destination_top_pick_name(
            suffix=DomainMetadataUploader.DESTINATION_TOP_PICK_FILE_NAME
        )
        self.remove_latest_from_all_top_picks_files(
            bucket_name=self.bucket_name,
            bucket=bucket,
            storage_client=self.storage_client,
        )
        latest_blob = bucket.blob(self.DESTINATION_TOP_PICK_FILE_NAME)
        latest_blob.upload_from_string(top_picks)
        dated_blob = bucket.blob(dst_top_pick_name)
        dated_blob.upload_from_string(top_picks)
        return dated_blob

    @staticmethod
    def _destination_top_pick_name(suffix: str) -> str:
        """Return the name of the top pick file to be used for uploading to GCS with timestamp."""
        current = datetime.now()
        return f"{int(current.timestamp())}_{suffix}"

    def remove_latest_from_all_top_picks_files(
        self,
        bucket_name: str,
        bucket: Bucket,
        storage_client: Client,
    ) -> None:
        """If an existing file with a timestamp and the `_latest` suffix exists,
        remove `_latest` so only the most recent file has the suffix.
        """
        blobs = storage_client.list_blobs(bucket_name)
        file_pattern = re.compile(r"\d+_top_picks_latest\.json")

        for blob in blobs:
            if re.search(file_pattern, blob):
                bucket.copy_blob(
                    blob=blob,
                    destination_bucket=bucket,
                    new_name=blob.name.replace("_latest", ""),
                )
                bucket.delete_blob(blob.name)
        return

    def get_latest_file_for_diff(
        self, client: Client
    ) -> dict[str, list[dict[str, str]]]:
        """Get the `_latest` top pick file with timestamp so a comparison
        can be made between the previous file and the new file to be written.
        """
        bucket: Bucket = client.get_bucket(self.bucket_name)
        domain_files = bucket.list_blobs(delimiter="/")
        file_pattern = re.compile(r"\d+_top_picks_latest\.json")

        for file in domain_files:
            if re.search(file_pattern, file):
                data = file.download_as_text()
                file_contents: dict = json.loads(data)
                logger.info(f"Domain file {file.name} acquired.")

                return file_contents
        return {"domains": []}

    def upload_favicons(self, src_favicons: list[str]) -> list[str]:
        """Upload the domain favicons to gcs using their source url and
        return the public urls of the uploaded ones.
        """
        dst_favicons: list = []
        bucket: Bucket = self.storage_client.bucket(self.bucket_name)
        for src_favicon in src_favicons:
            dst_favicon_public_url: str = ""
            favicon_image: FaviconImage | None = (
                self.favicon_downloader.download_favicon(src_favicon)
            )
            if favicon_image:
                try:
                    dst_favicon_name = self._destination_favicon_name(favicon_image)
                    dst_blob = bucket.blob(dst_favicon_name)

                    # upload favicon to gcs if force upload is set or if it doesn't exist there and
                    # make it publicly accessible
                    if self.force_upload or not dst_blob.exists():
                        logger.info(
                            f"Uploading favicon {src_favicon} to blob {dst_favicon_name}"
                        )
                        dst_blob.upload_from_string(
                            favicon_image.content,
                            content_type=favicon_image.content_type,
                        )
                        dst_blob.make_public()

                    dst_favicon_public_url = self._get_favicon_public_url(
                        dst_blob, dst_favicon_name
                    )
                    logger.info(f"favicon public url: {dst_favicon_public_url}")
                except Exception as e:
                    logger.info(f"Exception {e} occured while uploading {src_favicon}")

            dst_favicons.append(dst_favicon_public_url)

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
