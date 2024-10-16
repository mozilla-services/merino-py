"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

import json
import logging

from pydantic import BaseModel

from merino.curated_recommendations.prior_backends.protocol import Prior, PriorBackend
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)


class PriorStats(BaseModel):
    """Represents statistics exported to GCS to derive priors from."""

    region: str | None = None
    average_ctr_top2_items: float
    impressions_per_item: float


class GcsPrior(PriorBackend):
    """Backend that retrieves and caches Thompson sampling priors from Google Cloud Storage."""

    def __init__(self, synced_gcs_blob: SyncedGcsBlob) -> None:
        """Initialize the GcsPrior backend.

        Args:
            synced_gcs_blob: Instance of SyncedGcsBlob that manages GCS synchronization.
        """
        self._cache: dict[str | None, Prior] = {}  # cache keyed on region
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)

    @staticmethod
    def _derive_prior(prior_stats: PriorStats) -> Prior:
        # We calculate the beta parameter for Thompson sampling based on the average number of
        # impressions per item. Historically, beta was set to 15,600, which is approximately 10% of
        # the average impressions per item in the US on 2024-10-08 (180,827 impressions per item).
        # To maintain this proportion, we've chosen a weight of 0.1. A higher weight increases
        # exploration. Since having more items reduces the number of impressions available per item,
        # beta scales with the average impressions per item to adjust the level of exploration.
        beta = 0.1 * prior_stats.impressions_per_item
        # Set alpha to create an optimistic prior, so every item is explored to discover its CTR.
        alpha = beta * prior_stats.average_ctr_top2_items

        return Prior(region=prior_stats.region, alpha=alpha, beta=beta)

    def _fetch_callback(self, data: str) -> None:
        """Process the raw blob data and update the cache.

        Args:
            data: The blob string data, with an array of Prior objects.
        """
        prior_stats = [PriorStats(**item) for item in json.loads(data)]
        self._cache = {p.region: self._derive_prior(p) for p in prior_stats}

    def get(self, region: str | None = None) -> Prior | None:
        """Get Thompson sampling priors for the given region, if available.

        Args:
            region: The region for which to return prior data (e.g. 'US').

        Returns:
            Prior: The Thompson sampling prior for the given region, if available.
        """
        return self._cache.get(region)

    @property
    def update_count(self) -> int:
        """Return the number of times the prior data has been updated."""
        return self.synced_blob.update_count
