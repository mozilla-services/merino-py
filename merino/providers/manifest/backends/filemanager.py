"""A Filemanager to acquire data for the Manifest Provider (Remote-Only)."""

import json
import logging
from enum import Enum
from json import JSONDecodeError
from typing import Any

from google.cloud.storage import Bucket, Client

from merino.exceptions import FilemanagerError

logger = logging.getLogger(__name__)


class GetManifestResultCode(Enum):
    """Enum to capture the result of getting manifest file."""

    SUCCESS = 0
    FAIL = 1
    SKIP = 2


class ManifestFilemanagerError(FilemanagerError):
    """Error during interaction with Manifest data."""


class ManifestRemoteFilemanager:
    """Filemanager for fetching Manifest data from GCS and storing only in memory."""

    def __init__(
        self,
        gcs_project_path: str,
        gcs_bucket_path: str,
        blob_name: str,
    ) -> None:
        """:param gcs_project_path: Google Cloud project (or path to credentials).
        :param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_project_path = gcs_project_path
        self.gcs_bucket_path = gcs_bucket_path
        self.blob_name = blob_name

        # Track the last blob generation we downloaded.
        # If unchanged, we return SKIP to indicate no new data.
        self.blob_generation = 0

    def create_gcs_client(self) -> Client:
        """Initialize the GCS Client connection."""
        return Client(self.gcs_project_path)

    def get_file(self, client: Client) -> tuple[GetManifestResultCode, dict[str, Any] | None]:
        """Fetch the remote manifest file from GCS as an in-memory dict.

        :return: (GetManifestResultCode, dict or None)
        """
        try:
            bucket: Bucket = client.get_bucket(self.gcs_bucket_path)
            blob = bucket.get_blob(self.blob_name, if_generation_not_match=self.blob_generation)

            if blob is not None:
                # There's a new generation, so let's download it.
                self.blob_generation = blob.generation
                blob_data = blob.download_as_text()

                try:
                    manifest_content: dict = json.loads(blob_data)
                except JSONDecodeError as json_error:
                    logger.error("Failed to decode manifest JSON: %s", json_error)
                    return (GetManifestResultCode.FAIL, None)

                logger.info("Successfully loaded remote manifest file: %s", self.blob_name)
                return (GetManifestResultCode.SUCCESS, manifest_content)

            # If `get_blob` returned None, that usually means no new generation (SKIP).
            logger.debug(
                "No new GCS generation for '%s'; returning SKIP or blob doesn't exist.",
                self.blob_name,
            )
            return (GetManifestResultCode.SKIP, None)

        except Exception as e:
            logger.error("Error fetching remote manifest file '%s': %s", self.blob_name, e)
            return (GetManifestResultCode.FAIL, None)
