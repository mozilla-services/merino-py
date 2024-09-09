"""Wrapper for engagement data from Google Cloud Storage."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict

from google.cloud.storage import Client
from aiodogstatsd import Client as StatsdClient

from merino import cron
from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)

logger = logging.getLogger(__name__)

LAST_UPDATED_INITIAL_VALUE = datetime.min.replace(tzinfo=timezone.utc)


class GcsEngagement(EngagementBackend):
    """Backend that retrieves engagement data from Google Cloud Storage.

    This class periodically fetches engagement data from Google Cloud Storage in the background.
    """

    cron_task: asyncio.Task

    def __init__(
        self,
        storage_client: Client,
        metrics_client: StatsdClient,
        bucket_name: str,
        blob_prefix: str,
        max_size: int,
        cron_interval_seconds: float,
    ) -> None:
        """Initialize the engagement backend but do not start the background task.

        Args:
            storage_client: GCS client initialized to the correct project
            metrics_client: aiodogstatsd client for recording metrics
            bucket_name: GCS bucket name
            blob_prefix: GCS blob prefix
            max_size: Maximum size in bytes of the GCS blob. If exceeded, an error will be logged.
             and new engagement data will not be loaded. This guards against out-of-memory errors.
            cron_interval_seconds: Interval at which to check GCS for updates in seconds.
        """
        self.storage_client = storage_client
        self.metrics_client = metrics_client
        self.bucket_name = bucket_name
        self.blob_prefix = blob_prefix
        self.max_size = max_size
        self.cron_interval_seconds = cron_interval_seconds
        self.last_updated = LAST_UPDATED_INITIAL_VALUE
        self._update_count = 0
        self._cache: Dict[str, Engagement] = {}

    @property
    def update_count(self) -> int:
        """Return the number of times the engagement has been updated."""
        return self._update_count

    def initialize(self) -> None:
        """Start the background cron job to get new data."""
        cron_job = cron.Job(
            name="fetch_recommendation_engagement",
            interval=self.cron_interval_seconds,
            condition=lambda: True,
            task=self._update_task_async,
        )
        # Store the created task on the instance variable. Otherwise, it will get
        # garbage collected because asyncio's runtime only holds a weak reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    def get(self, scheduled_corpus_item_id: str) -> Engagement | None:
        """Get cached click and impression counts from the last 24h for the scheduled corpus item id

        Args:
            scheduled_corpus_item_id: The id of the scheduled corpus item for which
                                      to return engagement data.

        Returns:
            Engagement: Engagement data for the specified id if it exists in cache, otherwise None.
        """
        return self._cache.get(scheduled_corpus_item_id)

    async def _update_task_async(self) -> None:
        """Run _update_engagement_task in a thread to prevent blocking the event loop"""
        with self.metrics_client.timeit("recommendation.engagement.update.timing"):
            await asyncio.to_thread(self._update_task)

    def _update_task(self):
        """Task to update the cache with the latest engagement data from GCS."""
        bucket = self.storage_client.bucket(self.bucket_name)

        # Only list files from the last day (about 100) to reduce memory usage and requests to GCS.
        start_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d%H")
        start_offset = f"{self.blob_prefix}{start_date}"
        # Filter results to blobs whose names are lexicographically equal to or after start_offset.
        # https://cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.bucket.Bucket#google_cloud_storage_bucket_Bucket_list_blobs
        blobs = list(bucket.list_blobs(start_offset=start_offset))

        if not blobs:
            logger.error("Curated recommendations engagement blobs not found for start_offset")
            return

        # Find the most recent blob by the last modified timestamp.
        blob = max(blobs, key=lambda b: b.updated)

        self.metrics_client.gauge("recommendation.engagement.size", value=blob.size)

        if blob.size > self.max_size:
            logger.error(
                f"Curated recommendations engagement size {blob.size} exceeds {self.max_size}"
            )
        elif blob.updated <= self.last_updated:
            logger.info(f"Curated recommendations engagement unchanged since {self.last_updated}.")
        else:
            data = blob.download_as_text()
            engagement_data = self._parse_data(data)
            self._update_count += 1  # Increment the update count
            self._cache = engagement_data
            self.last_updated = blob.updated
            self.metrics_client.gauge(
                "recommendation.engagement.count", value=len(engagement_data)
            )

        # Report the staleness of the engagement data in seconds.
        if self.last_updated != LAST_UPDATED_INITIAL_VALUE:
            self.metrics_client.gauge(
                "recommendation.engagement.last_updated",
                value=time.time() - self.last_updated.timestamp(),
            )

    @staticmethod
    def _parse_data(data: str) -> Dict[str, Engagement]:
        """Parse the raw JSON data into a dictionary of Engagement objects."""
        raw_data = json.loads(data)
        return {item["scheduled_corpus_item_id"]: Engagement(**item) for item in raw_data}
