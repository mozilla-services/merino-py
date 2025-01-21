"""A Filemanager to retrieve data for the Manifest Provider (Remote-Only)."""

import json
import logging

from json import JSONDecodeError

from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Bucket, Client
from pydantic import ValidationError

from merino.providers.manifest.backends.protocol import ManifestData, GetManifestResultCode

logger = logging.getLogger(__name__)


class ManifestRemoteFilemanager:
    """Filemanager for fetching manifest data from GCS and storing only in memory."""

    blob_generation: int
    blob_name: str
    client: Client
    gcs_bucket_path: str
    gcs_project_path: str

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
        self.client = Client(self.gcs_project_path, credentials=AnonymousCredentials())

        # Track the last blob generation we downloaded.
        # If unchanged, we return SKIP to indicate no new data.
        self.blob_generation = 0

    def get_file(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the remote manifest file from GCS"""
        try:
            bucket: Bucket = self.client.get_bucket(self.gcs_bucket_path)
            blob = bucket.get_blob(self.blob_name, if_generation_not_match=self.blob_generation)

            if blob is not None:
                # There's a new generation, so let's download it.
                self.blob_generation = blob.generation
                blob_data = blob.download_as_text()

                try:
                    manifest_content = ManifestData.model_validate(json.loads(blob_data))
                except JSONDecodeError as json_error:
                    logger.error("Failed to decode manifest JSON: %s", json_error)
                    return (GetManifestResultCode.FAIL, None)
                except ValidationError as val_err:
                    logger.error(f"Invalid manifest content: {val_err}")
                    return (GetManifestResultCode.FAIL, None)

                logger.info("Successfully loaded remote manifest file: %s", self.blob_name)
                return (GetManifestResultCode.SUCCESS, manifest_content)

            # If `get_blob` returned None, that usually means no new generation (SKIP).
            logger.info(
                f"No new GCS generation for {self.blob_name}; returning SKIP or blob doesn't exist.",
            )
            return (GetManifestResultCode.SKIP, None)

        except Exception as e:
            logger.error(f"Error fetching remote manifest file {self.blob_name}: {e}")
            return (GetManifestResultCode.FAIL, None)
