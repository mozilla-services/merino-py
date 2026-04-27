# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Filemanager for retrieving engagement data from GCS."""

import logging
from json import JSONDecodeError

import orjson
from gcloud.aio.storage import Blob, Bucket, Storage
from pydantic import BaseModel

from merino.providers.suggest.adm.backends.protocol import KeywordEntry
from merino.utils.storage import get_storage_client


logger = logging.getLogger(__name__)


class EngagementData(BaseModel):
    """Model for the full engagement data file stored in GCS."""

    amp: dict[str, dict[str, str | int]] = {}
    amp_aggregated: dict[str, int] = {}
    wiki_aggregated: dict[str, int] = {}


class KeywordEngagementData(BaseModel):
    """Model for the keyword-level engagement data file stored in GCS."""

    amp: dict[str, KeywordEntry] = {}
    amp_aggregated: dict[str, int] = {}
    wiki_aggregated: dict[str, int] = {}


class EngagementFilemanager:
    """Filemanager for fetching engagement data from GCS asynchronously."""

    gcs_bucket_path: str
    blob_name: str
    gcs_client: Storage | None
    bucket: Bucket | None

    def __init__(self, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_bucket_path = gcs_bucket_path
        self.blob_name = blob_name
        self.gcs_client = None
        self.bucket = None

    def get_bucket(self) -> Bucket:
        """Return the configured bucket using shared storage client."""
        if self.bucket is not None:
            return self.bucket

        if self.gcs_client is None:
            self.gcs_client = get_storage_client()

        self.bucket = Bucket(storage=self.gcs_client, name=self.gcs_bucket_path)
        return self.bucket

    async def get_file(self) -> EngagementData | None:
        """Fetch the engagement data file from GCS and return a validated model instance."""
        try:
            bucket = self.get_bucket()
            blob: Blob = await bucket.get_blob(self.blob_name)
            blob_data = await blob.download()
            return EngagementData.model_validate(orjson.loads(blob_data))
        except (JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to decode engagement data JSON: {e}")
        except Exception as e:
            logger.error(f"Error fetching engagement data file {self.blob_name}: {e}")
        return None


class KeywordEngagementFilemanager:
    """Filemanager for fetching keyword-level engagement data from GCS asynchronously."""

    gcs_bucket_path: str
    blob_name: str
    gcs_client: Storage | None
    bucket: Bucket | None

    def __init__(self, gcs_bucket_path: str, blob_name: str) -> None:
        """:param gcs_bucket_path: GCS bucket name to fetch from.
        :param blob_name: Name of the blob in the GCS bucket.
        """
        self.gcs_bucket_path = gcs_bucket_path
        self.blob_name = blob_name
        self.gcs_client = None
        self.bucket = None

    def get_bucket(self) -> Bucket:
        """Return the configured bucket using shared storage client."""
        if self.bucket is not None:
            return self.bucket

        if self.gcs_client is None:
            self.gcs_client = get_storage_client()

        self.bucket = Bucket(storage=self.gcs_client, name=self.gcs_bucket_path)
        return self.bucket

    async def get_file(self) -> KeywordEngagementData | None:
        """Fetch the keyword engagement data file from GCS and return a validated model instance."""
        try:
            bucket = self.get_bucket()
            blob: Blob = await bucket.get_blob(self.blob_name)
            blob_data = await blob.download()
            return KeywordEngagementData.model_validate(orjson.loads(blob_data))
        except (JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to decode keyword engagement data JSON: {e}")
        except Exception as e:
            logger.error(f"Error fetching keyword engagement data file {self.blob_name}: {e}")
        return None
