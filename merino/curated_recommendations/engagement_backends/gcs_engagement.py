"""Wrapper for engagement data from Google Cloud Storage."""

import json
import logging
from collections import Counter

from aiodogstatsd import Client as StatsdClient

from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

EngagementKeyType = tuple[str | None, str | None]  # Keyed on (corpus_item_id, region)
EngagementCacheType = dict[EngagementKeyType, Engagement]


class GcsEngagement(EngagementBackend):
    """Backend that caches and periodically retrieves engagement data from Google Cloud Storage."""

    def __init__(
        self,
        synced_gcs_blob: SyncedGcsBlob,
        metrics_client: StatsdClient,
        metrics_namespace: str,
    ) -> None:
        """Initialize the GcsEngagement backend.

        Args:
            synced_gcs_blob: Instance of SyncedGcsBlob that manages GCS synchronization.
        """
        self._cache: EngagementCacheType = {}
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)
        self.metrics_client = metrics_client
        self.metrics_namespace = metrics_namespace

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Get cached click and impression counts from the last 24h for the corpus item id

        Args:
            corpus_item_id: The id of the corpus item for which to return engagement data.
            region: Return engagement for a given region (e.g. 'US'), or across all regions (None).

        Returns:
            Engagement: Engagement data for the specified id if it exists in cache, otherwise None.
        """
        return self._cache.get((corpus_item_id, region))

    @property
    def update_count(self) -> int:
        """Return the number of times the engagement data has been updated."""
        return self.synced_blob.update_count

    def _fetch_callback(self, data: str) -> None:
        """Process the raw engagement blob data and update the cache.

        Args:
            data: The engagement blob string data, with an array of Engagement objects.
        """
        parsed_data = [Engagement(**item) for item in json.loads(data)]
        next_cache = {}
        for engagement in parsed_data:
            cache_key = (engagement.corpus_item_id, engagement.region)
            prev_engagement = next_cache.get(cache_key, None)
            next_cache[cache_key] = engagement if prev_engagement is None else prev_engagement + engagement
        if len(next_cache) > 0:
            self._cache = next_cache
        self._track_metrics()

    def _track_metrics(self) -> None:
        """Emit statistics about engagement"""
        # Emit the total number of engagement records.
        self.metrics_client.gauge(f"{self.metrics_namespace}.count", value=len(self._cache))

        # Emit the number corpus items by region for which we have engagement data.
        region_counts = Counter(region for _, region in self._cache)
        for region, count in region_counts.items():
            region_name = region.lower() if region is not None else "global"
            self.metrics_client.gauge(f"{self.metrics_namespace}.{region_name}.count", value=count)

        # Sum clicks and impressions by region.
        clicks: Counter[str] = Counter()
        impressions: Counter[str] = Counter()
        report_counts: Counter[str] = Counter()
        for (item_id, region), eng in self._cache.items():
            region_name = region.lower() if region is not None else "global"
            clicks[region_name] += eng.click_count
            impressions[region_name] += eng.impression_count
            report_counts[region_name] += eng.report_count or 0  # report_count can be None

        # Emit clicks by region.
        for region, count in clicks.items():
            self.metrics_client.gauge(f"{self.metrics_namespace}.{region}.clicks", value=count)
        # Emit impressions by region.
        for region, count in impressions.items():
            self.metrics_client.gauge(
                f"{self.metrics_namespace}.{region}.impressions", value=count
            )
        # Emit report_counts by region.
        for region, count in report_counts.items():
            self.metrics_client.gauge(
                f"{self.metrics_namespace}.{region}.report_counts", value=count
            )
