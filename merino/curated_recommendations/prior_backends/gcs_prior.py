"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

import json
import logging

from merino.curated_recommendations.prior_backends.protocol import Prior, PriorBackend
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)


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

    def _fetch_callback(self, data: str) -> None:
        """Process the raw blob data and update the cache.

        Args:
            data: The blob string data, with an array of Prior objects.
        """
        parsed_data = [Prior(**item) for item in json.loads(data)]
        self._cache = {item.region: item for item in parsed_data}

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
