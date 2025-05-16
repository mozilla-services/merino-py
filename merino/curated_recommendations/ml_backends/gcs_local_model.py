"""Wrapper for local model data from Google Cloud Storage."""

import json
import logging
from typing import Any

from merino.curated_recommendations.ml_backends.protocol import (
    LocalModelBackend,
    InferredLocalModel,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)


class GCSLocalModel(LocalModelBackend):
    """Backend that caches and periodically retrieves model information from GCS"""

    def __init__(
        self,
        synced_gcs_blob: SyncedGcsBlob,
    ) -> None:
        """Initialize the GcsEngagement backend.

        Args:
            synced_gcs_blob: Instance of SyncedGcsBlob that manages GCS synchronization.
        """
        self._cache: dict[str | None, Any] = {}
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Get cached click and impression counts from the last 24h for the corpus item id

        Args:
            surface_id: Return model for a given surface (e.g. 'EN_US').

        Returns:
            Inferred local model
        """
        return self._cache.get(surface_id)

    @property
    def update_count(self) -> int:
        """Return the number of times the model data has been updated."""
        return self.synced_blob.update_count

    def _fetch_callback(self, data: str) -> None:
        """Process the raw model blob data and update the cache.

        Args:
            data: The engagement blob string data, with an array of Engagement objects.
        """
        parsed_data = [InferredLocalModel(**item) for item in json.loads(data)]
        self._cache = {d.surface_id: d for d in parsed_data}
