# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""A Filemanager to retrieve engagement data for the Wikipedia Provider."""

import logging
from json import JSONDecodeError

import orjson
from gcloud.aio.storage import Blob, Bucket, Storage

from merino.providers.suggest.wikipedia.backends.protocol import EngagementData

logger = logging.getLogger(__name__)


class WikipediaFilemanager:
    """Filemanager for fetching Wikipedia engagement data from GCS asynchronously and storing in memory."""

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

    async def get_bucket(self) -> Bucket:
        """Lazily instantiate the GCS client and return the configured bucket."""
        if self.bucket is not None:
            return self.bucket

        if self.gcs_client is None:
            self.gcs_client = Storage()

        self.bucket = Bucket(storage=self.gcs_client, name=self.gcs_bucket_path)
        return self.bucket

    async def get_file(self) -> EngagementData | None:
        """Fetch the Wikipedia engagement data file from GCS."""
        try:
            bucket = await self.get_bucket()
            blob: Blob = await bucket.get_blob(self.blob_name)
            blob_data = await blob.download()

            engagement_data = EngagementData.model_validate(orjson.loads(blob_data))

            logger.info(f"Successfully loaded Wikipedia engagement data from {self.blob_name}")

            return engagement_data

        except (JSONDecodeError, ValueError) as json_error:
            logger.error(f"Failed to decode Wikipedia engagement data JSON: {json_error}")

        except Exception as e:
            logger.error(f"Error fetching Wikipedia engagement data file {self.blob_name}: {e}")

        return None
