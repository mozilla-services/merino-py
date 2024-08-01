"""Wrapper for engagement data from Google Cloud Storage."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict

from google.cloud.storage import Client
from aiodogstatsd import Client as StatsdClient

from merino import cron
from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)

logger = logging.getLogger(__name__)


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
        blob_name: str,
        max_size: int,
        cron_interval: timedelta = timedelta(seconds=60),
    ) -> None:
        """Initialize the engagement backend but do not start the background task.

        Args:
            storage_client: GCS client initialized to the correct project
            metrics_client: aiodogstatsd client for recording metrics
            bucket_name: GCS bucket name
            blob_name: GCS blob path
            max_size: Maximum size in bytes of the GCS blob. If exceeded, an error will be logged
             and new engagement data will not be loaded. This guards against out-of-memory errors.
            cron_interval: Interval at which to check GCS for updates.
        """
        self.storage_client = storage_client
        self.metrics_client = metrics_client
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self.max_size = max_size
        self.cron_interval_sec = cron_interval
        self.last_updated = datetime.min
        self._cache: Dict[str, Engagement] = {}

    def initialize(self):
        """Start the background cron job to get new data."""
        # Run a cron job that resyncs data from Remote Settings in the background.
        cron_job = cron.Job(
            name="fetch_recommendation_engagement",
            interval=self.cron_interval_sec.total_seconds(),
            condition=lambda: True,
            task=self._update_task_async,
        )
        # Store the created task on the instance variable. Otherwise, it will get
        # garbage collected because asyncio's runtime only holds a weak reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    def __getitem__(self, scheduled_corpus_item_id: str) -> Engagement:
        """Get cached click and impression counts from the last 24h for the scheduled corpus item id

        Args:
            scheduled_corpus_item_id: The id of the scheduled corpus item for which
                                      to return engagement data.

        Returns:
            Engagement: This method always immediately returns an Engagement object containing
                        engagement data for the specified id. If the id does not exist in the
                        cache, the returned Engagement object will have 0 clicks and impressions.
        """
        if scheduled_corpus_item_id in self._cache:
            return self._cache[scheduled_corpus_item_id]
        return Engagement(
            scheduled_corpus_item_id=scheduled_corpus_item_id, clicks=0, impressions=0
        )

    async def _update_task_async(self) -> None:
        """Run _update_task in a thread to prevent blocking the event loop

        A thread is used because the Google Cloud library does not support asyncio.
        Alternatively, the gcloud-aio-storage library provides asyncio access to GCS.
        """
        await asyncio.to_thread(self._update_task)

    def _update_task(self):
        """Task to update the cache with the latest engagement data from GCS."""
        with self.metrics_client.timeit("recommendation.engagement.update.timing"):
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            # Reload properties from Cloud Storage. This populates blob.size and blob.updated.
            blob.reload()

            self.metrics_client.gauge("recommendation.engagement.size", value=blob.size)

            if blob.size > self.max_size:
                logger.error(
                    f"Curated recommendations engagement size {blob.size} exceeds {self.max_size}"
                )
            elif blob.updated <= self.last_updated:
                logger.info(
                    f"Curated recommendations engagement unchanged since {self.last_updated}."
                )
            else:
                data = blob.download_as_text()
                engagement_data = self._parse_data(data)
                self._cache = engagement_data
                self.last_updated = blob.updated
                self.metrics_client.gauge(
                    "recommendation.engagement.count", value=len(engagement_data)
                )

            # Report the staleness of the engagement data in seconds.
            if self.last_updated != datetime.min:
                self.metrics_client.gauge(
                    "recommendation.engagement.last_updated",
                    value=time.time() - self.last_updated.timestamp(),
                )

    @staticmethod
    def _parse_data(data: str) -> Dict[str, Engagement]:
        """Parse the raw JSON data into a dictionary of Engagement objects."""
        raw_data = json.loads(data)
        return {item["scheduled_corpus_item_id"]: Engagement(**item) for item in raw_data}
