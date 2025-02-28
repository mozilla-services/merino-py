"""A Filemanager to retrieve data for the Manifest Provider (Remote-Only)."""

import orjson
import logging

from json import JSONDecodeError

from pydantic import ValidationError

from merino.providers.manifest.backends.protocol import ManifestData, GetManifestResultCode
from gcloud.aio.storage import Blob, Bucket, Storage
from merino.utils.metrics import get_metrics_client

logger = logging.getLogger(__name__)

## TODO use this probably for blob generation logic
""" async def download(
    self, bucket: str, object_name: str, *,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[Session] = None,
) -> bytes:
    return await self._download(
        bucket, object_name, headers=headers,
        timeout=timeout, params={'alt': 'media'},
        session=session,
    )"""
class ManifestRemoteFilemanager:
    """Filemanager for fetching manifest data from GCS and storing only in memory."""

    gcs_client: Storage
    blob_name: str
    blob_generation: int

    def __init__(self, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_client = Storage()
        self.blob_name = blob_name
        self.bucket = Bucket(storage=self.gcs_client, name=gcs_bucket_path)

        # TODO figure out this
        self.blob_generation = 0

    async def get_file(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the remote manifest file from GCS"""
        metrics_client = get_metrics_client()

        try:
            # TODO
            # blob.reload()
            blob: Blob = await self.bucket.get_blob(self.blob_name)
            blob_data = await blob.download()

            metrics_client.gauge("manifest.size", value=blob.size)

            manifest_content = ManifestData.model_validate(orjson.loads(blob_data))
            metrics_client.gauge("manifest.domains.count", value=len(manifest_content.domains))

            logger.info("Successfully loaded remote manifest file: %s", self.blob_name)
            return GetManifestResultCode.SUCCESS, manifest_content

        except JSONDecodeError as json_error:
            logger.error("Failed to decode manifest JSON: %s", json_error)
            return GetManifestResultCode.FAIL, None
        except ValidationError as val_err:
            logger.error(f"Invalid manifest content: {val_err}")
            return GetManifestResultCode.FAIL, None
        except Exception as e:
            logger.error(f"Error fetching remote manifest file {self.blob_name}: {e}")
            return GetManifestResultCode.FAIL, None
