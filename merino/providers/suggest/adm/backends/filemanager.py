# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""A Filemanager to retrieve data for the ADM Provider."""

import orjson
import logging

from json import JSONDecodeError
from gcloud.aio.storage import Blob, Bucket, Storage

from merino.providers.suggest.adm.backends.protocol import EngagementData

logger = logging.getLogger(__name__)


class ADMFilemanager:
    """Filemanager for fetching engagement data from GCS asynchronously and storing in memory."""

    gcs_bucket_path: str
    blob_name: str
    gcs_client: Storage | None = None
    bucket: Bucket | None = None

    def __init__(self, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_bucket_path = gcs_bucket_path
        self.blob_name = blob_name

    def get_bucket(self) -> Bucket:
        """Lazily instantiate the GCS client and return the configured bucket"""
        if self.bucket is not None:
            return self.bucket

        if self.gcs_client is None:
            self.gcs_client = Storage()

        self.bucket = Bucket(storage=self.gcs_client, name=self.gcs_bucket_path)
        return self.bucket

    async def get_file(self) -> EngagementData | None:
        """Fetch the engagement data file from GCS"""
        try:
            bucket = self.get_bucket()
            blob: Blob = await bucket.get_blob(self.blob_name)
            blob_data = await blob.download()

            engagement_data = EngagementData.model_validate(orjson.loads(blob_data))

            logger.info(f"Successfully loaded engagement data from {self.blob_name}")

            return engagement_data

        except (JSONDecodeError, ValueError) as json_error:
            logger.error(f"Failed to decode engagement data JSON: {json_error}")

        except Exception as e:
            logger.error(f"Error fetching engagement data file {self.blob_name}: {e}")
        return None
