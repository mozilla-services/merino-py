"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

from datetime import datetime, timedelta, timezone
from functools import partial
import json
import logging

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.ml_backends.protocol import (
    MLRecsBackend,
    ContextualArticleRankings,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

GLOBAL_KEY = "global"

VALIDITY_PERIOD_MINUTES = 60  # If job gets backed up, we have a thompson sampling fallback

DEFAULT_SURFACE_ID = SurfaceId.NEW_TAB_EN_US


class GcsMLRecs(MLRecsBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self, synced_gcs_blobs: dict[SurfaceId, SyncedGcsBlob]) -> None:
        self._cache: dict[SurfaceId, dict[str, ContextualArticleRankings]] = {}
        self.synced_blobs: dict[SurfaceId, SyncedGcsBlob] = synced_gcs_blobs
        for surface_id, synced_blob in self.synced_blobs.items():
            synced_blob.set_fetch_callback(partial(self._fetch_callback, surface_id=surface_id))
        self.cache_time: dict[SurfaceId, datetime] = {}
        self.cohort_training_run_id: dict[SurfaceId, str | None] = {}
        self._impression_counts: dict[SurfaceId, dict[str, int]] = {}

    @staticmethod
    def _generate_cache_keys(
        region: str | None, cohort: str | None, time_zone: str | None = None
    ) -> dict[str, str]:
        """Never return Nones; normalize to strings."""
        r = (region or "").strip().upper()
        c = (f"COHORT_{cohort}" if cohort else "").strip()
        tz = (f"TZ_{time_zone}" if time_zone else "").strip()
        return {
            "region_cohort_tz": f"{r}_{c}_{tz}" if (r or c or tz) else GLOBAL_KEY,
            "region_cohort": f"{r}_{c}" if (r or c) else GLOBAL_KEY,
            "region": r,
            "global": GLOBAL_KEY,
        }

    def _fetch_callback(self, data: str, surface_id: SurfaceId) -> None:
        """Process the raw blob data and update the cache atomically."""
        payload = json.loads(data)
        slates = payload.get("slates") or {}
        epoch_id = payload.get("epoch_id", None)

        new_cache: dict[str, ContextualArticleRankings] = {}
        for context_str, slate in slates.items():
            new_cache[context_str] = ContextualArticleRankings(**slate)
        if epoch_id:
            self.cache_time[surface_id] = datetime.strptime(epoch_id, "%Y%m%d-%H%M").replace(
                tzinfo=timezone.utc
            )
        self._impression_counts[surface_id] = payload.get("impressions_by_id", {})
        self.cohort_training_run_id[surface_id] = payload.get("cohort_model", {}).get(
            "training_run_id", None
        )
        self._cache[surface_id] = new_cache

    def get(
        self,
        surface_id: SurfaceId,
        region: str | None = None,
        cohort: str | None = None,
        time_zone: str | None = None,
    ) -> ContextualArticleRankings | None:
        """Fetch the recommendations based on region and utc offset"""
        cache = self._cache.get(surface_id)
        if not cache:
            return None
        keys = self._generate_cache_keys(region, cohort, time_zone)
        # Probe in order of specificity
        ro = keys["region_cohort_tz"]
        if ro and ro in cache:
            return cache[ro]
        ro = keys["region_cohort"]
        if ro and ro in cache:
            return cache[ro]
        r = keys["region"]
        if r and r in cache:
            return cache[r]
        return cache.get(GLOBAL_KEY, None)

    def get_adjusted_impressions(self, corpus_item_id: str, surface_id: SurfaceId) -> int:
        """Return the impression count for a given corpus item id (adjusted for propensity)"""
        return self._impression_counts.get(surface_id, {}).get(corpus_item_id, 0)

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return whether the backend is valid and ready to serve recommendations."""
        cache = self._cache.get(surface_id)
        cache_time = self.cache_time.get(surface_id)
        impressions = self._impression_counts.get(surface_id)
        return (
            cache is not None
            and len(cache) > 0
            and cache_time is not None
            and (
                datetime.now(timezone.utc) - cache_time
                <= timedelta(minutes=VALIDITY_PERIOD_MINUTES)
            )
            and impressions is not None
            and len(impressions) > 0
        )

    def get_cohort_training_run_id(self, surface_id: SurfaceId) -> str | None:
        """Return the training run ID for the cohort model used."""
        return self.cohort_training_run_id.get(surface_id)

    @property
    def update_count(self) -> int:
        """Return the number of times the ml data has been updated across all blobs."""
        return sum(blob.update_count for blob in self.synced_blobs.values())
