# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module providing a class to manage synchronized blobs from Google Cloud Storage."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from google.cloud.storage import Client
from aiodogstatsd import Client as StatsdClient

from merino.utils import cron
from merino.config import settings

logger = logging.getLogger(__name__)


LAST_UPDATED_INITIAL_VALUE = datetime.min.replace(tzinfo=timezone.utc)


class SyncedGcsBlob:
    """Class to manage a synchronized Google Cloud Storage blob.

    This class periodically fetches data from a GCS blob in the background.
    """

    cron_task: asyncio.Task

    def __init__(
        self,
        storage_client: Client,
        metrics_client: StatsdClient,
        metrics_namespace: str,
        bucket_name: str,
        blob_name: str,
        max_size: int,
        cron_interval_seconds: float,
        cron_job_name: str,
    ) -> None:
        """Initialize the SyncedGcsBlob instance.

        Args:
            storage_client: GCS client initialized to the correct project.
            metrics_client: aiodogstatsd client for recording metrics.
            metrics_namespace: Namespace for metrics to distinguish different instances.
            bucket_name: GCS bucket name.
            blob_name: Full path to the GCS blob.
            max_size: Maximum size in bytes of the GCS blob. If exceeded, an error will be logged.
            cron_interval_seconds: Interval at which to check GCS for updates in seconds.
        """
        self.storage_client = storage_client
        self.metrics_client = metrics_client
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self.max_size = max_size
        self.cron_interval_seconds = cron_interval_seconds
        self.cron_job_name = cron_job_name
        self.metrics_namespace = metrics_namespace
        self.fetch_callback: Callable[[str], None] | None = None
        self.last_updated = LAST_UPDATED_INITIAL_VALUE
        self._update_count = 0

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

    def set_fetch_callback(self, fetch_callback: Callable[[str], None]) -> None:
        """Set the fetch callback function.

        Args:
            fetch_callback: A callable that processes the raw blob data.
        """
        self.fetch_callback = fetch_callback

    async def _start_cron_job(self) -> None:
        """Start the background cron job to update data periodically."""
        while True:
            await self._update_task_async()
            await asyncio.sleep(self.cron_interval_seconds)

    async def _update_task_async(self) -> None:
        """Run _update_task in a thread to prevent blocking the event loop."""
        with self.metrics_client.timeit(f"{self.metrics_namespace}.update.timing"):
            await asyncio.to_thread(self._update_task)

    def _update_task(self) -> None:
        """Task to update the data with the latest data from GCS."""
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(self.blob_name)

        if not blob.exists():
            # The staging bucket is not expected to have data. We don't want to emit a Sentry error.
            level = logging.INFO if settings.current_env.lower() == "stage" else logging.ERROR
            logger.log(level, f"Blob '{self.blob_name}' not found.")
            return

        # reload() populates blob.size and blob.updated.
        blob.reload()
        self.metrics_client.gauge(f"{self.metrics_namespace}.size", value=blob.size)

        if blob.size > self.max_size:
            logger.error(f"Blob '{blob.name}' size {blob.size} exceeds {self.max_size}")
        elif blob.updated <= self.last_updated:
            logger.info(f"{blob.name} unchanged since {self.last_updated}.")
        else:
            data = blob.download_as_text()
            if self.fetch_callback:
                self.fetch_callback(data)
                self._update_count += 1
                self.last_updated = blob.updated
            else:
                logger.warning("Fetch callback is not set. Ignoring fetched data.")

        # Report the staleness of the data in seconds.
        if self.last_updated != LAST_UPDATED_INITIAL_VALUE:
            self.metrics_client.gauge(
                f"{self.metrics_namespace}.last_updated",
                value=time.time() - self.last_updated.timestamp(),
            )
