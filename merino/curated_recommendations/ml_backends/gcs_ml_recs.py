"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

from datetime import datetime, timedelta, timezone
import json
import logging

from merino.curated_recommendations.ml_backends.protocol import (
    MLRecsBackend,
    ContextualArticleRankings,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

GLOBAL_KEY = "global"

VALIDITY_PERIOD_MINUTES = 60  # If job gets backed up, we have a thompson sampling fallback


class GcsMLRecs(MLRecsBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self, synced_gcs_blob: SyncedGcsBlob) -> None:
        self._cache: dict[str, ContextualArticleRankings] = {}  # string keys only
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)
        self.cache_time: datetime | None = None
        self.cohort_training_run_id: str | None = None

    @staticmethod
    def _generate_cache_keys(
        region: str | None, utcOffset: str | None, cohort: str | None
    ) -> dict[str, str]:
        """Never return Nones; normalize to strings."""
        r = (region or "").strip().upper()
        o = (utcOffset or "").strip()
        c = (f"COHORT_{cohort}" if cohort else "").strip()
        return {
            "region_cohort": f"{r}_{c}" if (r or c) else GLOBAL_KEY,
            "region_offset": f"{r}_{o}" if (r or o) else GLOBAL_KEY,
            "region": r,
            "global": GLOBAL_KEY,
        }

    def _fetch_callback(self, data: str) -> None:
        """Process the raw blob data and update the cache atomically."""
        payload = json.loads(data)
        slates = payload.get("slates") or {}
        epoch_id = payload.get("epoch_id", None)

        new_cache: dict[str, ContextualArticleRankings] = {}
        for context_str, slate in slates.items():
            new_cache[context_str] = ContextualArticleRankings(**slate)
        if epoch_id:
            self.cache_time = datetime.strptime(epoch_id, "%Y%m%d-%H%M").replace(
                tzinfo=timezone.utc
            )
        self._impression_counts: dict[str, int] = payload.get("impressions_by_id", {})

        self.cohort_training_run_id = payload.get("cohort_model", {}).get("training_run_id", None)
        self._cache = new_cache

    def get(
        self, region: str | None = None, utcOffset: str | None = None, cohort: str | None = None
    ) -> ContextualArticleRankings | None:
        """Fetch the recommendations based on region and utc offset"""
        print("Fetching ML Recs with region:", region, "utcOffset:", utcOffset, "cohort:", cohort)
        keys = self._generate_cache_keys(region, utcOffset, cohort)
        # Probe in order of specificity
        ro = keys["region_cohort"]
        if ro and ro in self._cache:
            print(ro)
            return self._cache[ro]
        ro = keys["region_offset"]
        if ro and ro in self._cache:
            return self._cache[ro]
        r = keys["region"]
        if r and r in self._cache:
            print(ro)
            return self._cache[r]
        return self._cache.get(GLOBAL_KEY, None)

    def get_adjusted_impressions(self, corpus_item_id: str) -> int:
        """Return the impression count for a given corpus item id (adjusted for propensity)"""
        return self._impression_counts.get(corpus_item_id, 0)

    def is_valid(self) -> bool:
        """Return whether the backend is valid and ready to serve recommendations."""
        return (
            self._cache is not None
            and len(self._cache) > 0
            and self.cache_time is not None
            and (
                datetime.now(timezone.utc) - self.cache_time
                <= timedelta(minutes=VALIDITY_PERIOD_MINUTES)
            )
            and self._impression_counts is not None
            and len(self._impression_counts) > 0
        )

    def get_cohort_training_run_id(self) -> str | None:
        """Return the training run ID for the cohort model used."""
        return self.cohort_training_run_id

    @property
    def update_count(self) -> int:
        """Return the number of times the ml data has been updated."""
        return self.synced_blob.update_count
