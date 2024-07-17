"""Wrapper for engagement data from Google Cloud Storage."""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict

from google.cloud.storage import Client
from aiodogstatsd import Client as StatsdClient
from .protocol import Engagement, EngagementBackend

logger = logging.getLogger(__name__)


class GcsEngagement(EngagementBackend):
    """Backend that retrieves engagement data from Google Cloud Storage.

    This class fetches engagement data from Google Cloud Storage in a background thread.
    A thread is used because the Google Cloud library does not support asyncio. This class uses
    a single thread with a low request rate to GCS, ensuring thread performance is not an issue.
    Alternatively, the gcloud-aio-storage library provides asyncio access to GCS.
    """

    _thread: threading.Thread | None

    def __init__(
        self,
        storage_client: Client,
        metrics_client: StatsdClient,
        bucket_name: str,
        blob_name: str,
        max_size: int,
        thread_sleep_period: timedelta = timedelta(seconds=1),
        gcs_check_interval: timedelta = timedelta(seconds=60),
    ) -> None:
        """Initialize the engagement backend but do not start the background task.

        Args:
            storage_client: GCS client initialized to the correct project
            metrics_client: aiodogstatsd client for recording metrics
            bucket_name: GCS bucket name
            blob_name: GCS blob path
            max_size: Maximum size in bytes of the GCS blob. If exceeded, an error will be logged
             and new engagement data will not be loaded. This guards against out-of-memory errors.
            thread_sleep_period: Max time that thread will stay alive after shutdown() is called.
            gcs_check_interval: Interval at which to check GCS for updates.
        """
        self.storage_client = storage_client
        self.metrics_client = metrics_client
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self.max_size = max_size
        self.thread_sleep_period = thread_sleep_period
        self.gcs_check_interval = gcs_check_interval
        self.last_updated = datetime.min
        self._cache: Dict[str, Engagement] = {}
        self._shutdown_event = threading.Event()
        self._thread = None

    def initialize(self):
        """Start the background thread to get new data."""
        self._thread = threading.Thread(target=self._update_cache_loop, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        """Clean up resources and stop the cache update loop."""
        self._shutdown_event.set()
        if self._thread:
            self._thread.join()
        self.storage_client.close()

    def __getitem__(self, scheduled_corpus_item_id: str) -> Engagement:
        """Get engagement data for the given scheduled corpus item id from cache.

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

    def _update_task(self):
        """Task to update the cache with the latest engagement data from GCS."""
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(self.blob_name)
        # Reload properties from Cloud Storage. This populates blob.size and blob.updated.
        blob.reload()

        self.metrics_client.gauge("recommendation.engagement.size", value=blob.size)

        if blob.size > self.max_size:
            logger.error(f"Curated recommendations engagement size {blob.size} > {self.max_size}")
        elif blob.updated <= self.last_updated:
            logger.info(f"Curated recommendations engagement unchanged since {self.last_updated}.")
        else:
            data = blob.download_as_text()
            engagement_data = self._parse_data(data)
            self._cache = engagement_data
            self.last_updated = blob.updated
            self.metrics_client.gauge(
                "recommendation.engagement.count", value=len(engagement_data)
            )

    def _update_cache_loop(self):
        """Loop to periodically update the cache with the latest engagement data from GCS."""
        next_update_time = datetime.now()

        while not self._shutdown_event.is_set():
            try:
                if datetime.now() >= next_update_time:
                    next_update_time += self.gcs_check_interval
                    with self.metrics_client.timeit("recommendation.engagement.update.timing"):
                        self._update_task()
            except Exception as e:
                # Log unexpected exceptions to Sentry, and retry the update in the next interval.
                logger.error(f"GcsEngagement failed to update cache: {e}")
            finally:
                # Sleep between request (success or failure) to limit resource usage.
                time.sleep(self.thread_sleep_period.total_seconds())
                # Report the staleness of the engagement data in seconds.
                self.metrics_client.gauge(
                    "recommendation.engagement.last_updated",
                    value=time.time() - self.last_updated.timestamp(),
                )

    @staticmethod
    def _parse_data(data: str) -> Dict[str, Engagement]:
        """Parse the raw JSON data into a dictionary of Engagement objects."""
        raw_data = json.loads(data)
        return {item["scheduled_corpus_item_id"]: Engagement(**item) for item in raw_data}
