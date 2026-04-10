# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module providing a class to manage synchronized blobs from Google Cloud Storage."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Callable, Generic, Optional, TypeVar

import aiohttp
import orjson
from aiodogstatsd import Client as StatsdClient
from aiodogstatsd.typedefs import MTags
from gcloud.aio.storage import Blob, Bucket, Storage
from pydantic import BaseModel, ValidationError

from merino.utils import cron


logger = logging.getLogger(__name__)


LAST_UPDATED_INITIAL_VALUE = datetime.min.replace(tzinfo=timezone.utc)

T = TypeVar("T", bound=BaseModel)


class SyncedGcsBlobV2(Generic[T]):
    """Class to manage a synchronized Google Cloud Storage blob.

    This class periodically fetches data from a GCS blob in the background.
    """

    cron_task: asyncio.Task
    last_updated: datetime
    metrics_namespace = "gcs.sync"
    _data: Optional[T]

    def __init__(
        self,
        storage_client: Storage,
        metrics_client: StatsdClient,
        bucket_name: str,
        blob_name: str,
        max_size: int,
        cron_interval_seconds: float,
        cron_job_name: str,
        fetch_callback: Callable[[bytes], T],
    ) -> None:
        """Initialize the SyncedGcsBlob instance.

        Args:
            storage_client: Async GCS client (gcloud.aio.storage.Storage).
            metrics_client: aiodogstatsd client for recording metrics.
            bucket_name: GCS bucket name.
            blob_name: Full path to the GCS blob.
            max_size: Maximum size in bytes of the GCS blob. If exceeded, an error will be logged.
            cron_interval_seconds: Interval at which to check GCS for updates in seconds.
            cron_job_name: Name for the cron job
            fetch_callback: callback invoked upon fetched data.
        """
        self.storage_client = storage_client
        self.metrics_client = metrics_client
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self.max_size = max_size
        self.cron_interval_seconds = cron_interval_seconds
        self.cron_job_name = cron_job_name
        self.fetch_callback = fetch_callback
        self.last_updated = LAST_UPDATED_INITIAL_VALUE
        self._update_count = 0
        self._bucket = Bucket(storage=storage_client, name=bucket_name)
        self._default_tags: MTags = {"bucket": self.bucket_name, "blob": self.blob_name}
        self._data = None

    def initialize(self) -> None:
        """Start the background cron job to get new data."""
        cron_job = cron.Job(
            name=self.cron_job_name,
            interval=self.cron_interval_seconds,
            condition=lambda: True,
            task=self._update_task_async,
        )
        # Store the created task on the instance variable. Otherwise, it will get
        # garbage collected because asyncio's runtime only holds a weak reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    @property
    def update_count(self) -> int:
        """Return the number of times the data has been updated."""
        return self._update_count

    @property
    def data(self) -> Optional[T]:
        """Returns the synced data processed with fetch_callback,
        or None if it is not yet available (or failed to fetch).
        """
        if self._data is None:
            logger.error("Synced data accessed before it is available")
            self.metrics_client.increment(
                f"{SyncedGcsBlobV2.metrics_namespace}.unavailable", tags=self._default_tags
            )
        return self._data

    async def _update_task_async(self) -> None:
        """Fetch the latest data from GCS and invoke the appropriate callback."""
        with self.metrics_client.timeit(
            f"{self.metrics_namespace}.update.timing", tags=self._default_tags
        ):
            await self._update_task()

    def _gauge_validity(self, value: int):
        self.metrics_client.gauge(
            f"{SyncedGcsBlobV2.metrics_namespace}.valid", value=value, tags=self._default_tags
        )

    def _increment_fetch_status(self, status_code: int):
        self.metrics_client.increment(
            f"{self.metrics_namespace}.fetch.response",
            tags={**self._default_tags, "status": status_code},
        )

    async def _update_task(self) -> None:
        """Task to update the data with the latest data from GCS."""
        try:
            blob: Blob = await self._bucket.get_blob(self.blob_name)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                logger.error(f"Blob '{self.blob_name}' not found.")
                self._increment_fetch_status(e.status)
            else:
                logger.error(f"Error fetching blob metadata for '{self.blob_name}': {e}")
                self._increment_fetch_status(e.status)
            return

        self._increment_fetch_status(200)

        blob_size = int(blob.size)
        blob_updated = datetime.fromisoformat(blob.updated)

        self.metrics_client.gauge(
            f"{self.metrics_namespace}.size", value=blob_size, tags=self._default_tags
        )
        if blob_size > self.max_size:
            logger.error(f"Blob '{self.blob_name}' size {blob_size} exceeds {self.max_size}")
            self._gauge_validity(0)
        elif blob_updated <= self.last_updated:
            logger.info(f"{self.blob_name} unchanged since {self.last_updated}.")
            # Set last_updated as this data is not stale, just unchanged
            self.last_updated = blob_updated
        else:
            raw: bytes = await blob.download()
            try:
                result = self.fetch_callback(raw)
                self._data = result
                self._update_count += 1
                self.last_updated = blob_updated
                self._gauge_validity(1)
            except JSONDecodeError as json_error:
                self._gauge_validity(0)
                logger.error(f"Failed to decode blob JSON: {json_error}")
            except ValidationError as val_err:
                self._gauge_validity(0)
                logger.error(f"Invalid blob content: {val_err}")
            except Exception as generic_err:
                self._gauge_validity(0)
                logger.error(f"Blob fetch failure: {generic_err}")

        # Report the staleness of the data in seconds.
        if self.last_updated != LAST_UPDATED_INITIAL_VALUE:
            self.metrics_client.gauge(
                f"{self.metrics_namespace}.last_updated",
                value=time.time() - self.last_updated.timestamp(),
                tags=self._default_tags,
            )


def typed_gcs_json_blob_factory(
    model: type[T],
    storage_client: Storage,
    metrics_client: StatsdClient,
    bucket_name: str,
    blob_name: str,
    max_size: int,
    cron_interval_seconds: float,
    cron_job_name: str,
) -> SyncedGcsBlobV2[T]:
    """Generate a SyncedGcsBlobV2 object
    which pulls and validates a JSON file according to the
    provided pydantic model.
    Raises errors if JSON is invalid or model validation fails,
    to be handled by the caller.
    """

    def fetch_callback(data: bytes) -> T:
        default_tags: MTags = {"bucket": bucket_name, "blob": blob_name}
        parsed = model.model_validate(orjson.loads(data))
        metrics_client.gauge(
            f"{SyncedGcsBlobV2.metrics_namespace}.valid", value=1, tags=default_tags
        )
        return parsed

    return SyncedGcsBlobV2(
        storage_client,
        metrics_client,
        bucket_name,
        blob_name,
        max_size,
        cron_interval_seconds,
        cron_job_name,
        fetch_callback,
    )
