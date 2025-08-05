# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""A Filemanager to retrieve data for the Polygon Provider."""

from datetime import datetime
import orjson
import logging

from json import JSONDecodeError
from pydantic import ValidationError
from gcloud.aio.storage import Blob, Bucket, Storage

from merino.providers.suggest.finance.backends.protocol import (
    GetManifestResultCode,
    FinanceManifest,
)

logger = logging.getLogger(__name__)


class PolygonFilemanager:
    """Filemanager for fetching logo data from GCS asynchronously and storing only in memory."""

    gcs_client: Storage
    blob_name: str
    bucket: Bucket

    def __init__(self, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_storage_client = Storage()
        self.blob_name = blob_name
        self.bucket = Bucket(storage=self.gcs_storage_client, name=gcs_bucket_path)

    async def get_file(self) -> tuple[GetManifestResultCode, FinanceManifest | None, float | None]:
        """Fetch the manifest file and the updated timestamp from GCS"""
        try:
            blob: Blob = await self.bucket.get_blob(self.blob_name)
            blob_data = await blob.download()

            manifest_content = FinanceManifest.model_validate(orjson.loads(blob_data))

            # retrieve time stamp
            updated_ts = None
            updated_str = getattr(blob, "updated", None)
            if isinstance(updated_str, str):
                try:
                    updated_ts = datetime.strptime(
                        updated_str, "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).timestamp()
                except ValueError as parse_err:
                    logger.warning(f"Could not parse blob.updated: {updated_str} ({parse_err})")
            logger.info(
                f"Successfully loaded finance manifest file: {self.blob_name}, timestamp:{updated_ts}"
            )

            return GetManifestResultCode.SUCCESS, manifest_content, updated_ts

        except JSONDecodeError as json_error:
            logger.error("Failed to decode finance manifest JSON: %s", json_error)

        except ValidationError as val_err:
            logger.error(f"Invalid finance manifest content: {val_err}")

        except Exception as e:
            logger.error(f"Error fetching finance manifest file {self.blob_name}: {e}")
        return GetManifestResultCode.FAIL, None, None
