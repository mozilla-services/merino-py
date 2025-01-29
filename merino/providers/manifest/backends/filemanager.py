"""A Filemanager to retrieve data for the Manifest Provider (Remote-Only)."""

import json
import logging

from json import JSONDecodeError

from pydantic import ValidationError

from merino.providers.manifest.backends.protocol import ManifestData, GetManifestResultCode
from merino.utils.gcs.gcp_uploader import GcsUploader
from merino.utils.metrics import get_metrics_client

logger = logging.getLogger(__name__)


class ManifestRemoteFilemanager:
    """Filemanager for fetching manifest data from GCS and storing only in memory."""

    gcs_client: GcsUploader
    blob_name: str
    blob_generation: int

    def __init__(self, gcs_project_path: str, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_project_path: Google Cloud project.
        :param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_client = GcsUploader(gcs_project_path, gcs_bucket_path, "")
        self.blob_name = blob_name
        self.blob_generation = 0

    def get_file(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the remote manifest file from GCS"""
        metrics_client = get_metrics_client()

        try:
            blob = self.gcs_client.get_file_by_name(self.blob_name, self.blob_generation)

            if blob is not None:
                blob.reload()
                metrics_client.gauge("manifest.size", value=blob.size)

                blob_data = blob.download_as_text()

                try:
                    manifest_content = ManifestData.model_validate(json.loads(blob_data))
                    metrics_client.gauge(
                        "manifest.domains.count", value=len(manifest_content.domains)
                    )
                except JSONDecodeError as json_error:
                    logger.error("Failed to decode manifest JSON: %s", json_error)
                    return GetManifestResultCode.FAIL, None
                except ValidationError as val_err:
                    logger.error(f"Invalid manifest content: {val_err}")
                    return GetManifestResultCode.FAIL, None

                logger.info("Successfully loaded remote manifest file: %s", self.blob_name)
                return GetManifestResultCode.SUCCESS, manifest_content

            # If `get_file_by_name` returned None, that usually means no new generation (SKIP).
            logger.info(
                f"No new GCS generation for {self.blob_name}; returning SKIP or blob doesn't exist.",
            )
            return GetManifestResultCode.SKIP, None

        except Exception as e:
            logger.error(f"Error fetching remote manifest file {self.blob_name}: {e}")
            return GetManifestResultCode.FAIL, None
