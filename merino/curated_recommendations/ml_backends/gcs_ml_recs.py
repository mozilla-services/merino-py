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

    @staticmethod
    def _generate_cache_keys(region: str | None, utcOffset: str | None) -> dict[str, str]:
        """Never return Nones; normalize to strings."""
        r = (region or "").strip().upper()
        o = (utcOffset or "").strip()
        return {
            "region_offset": f"{r}_{o}" if (r or o) else GLOBAL_KEY,
            "region": r,
            "global": GLOBAL_KEY,
        }

    def _fetch_callback(self, data: bytes | str) -> None:
        """Process the raw blob data and update the cache atomically."""
        payload = json.loads(data if isinstance(data, str) else data.decode("utf-8"))
        slates = payload.get("slates") or {}
        epoch_id = payload.get("epoch_id", None)

        new_cache: dict[str, ContextualArticleRankings] = {}
        for context_str, slate in slates.items():
            new_cache[context_str] = ContextualArticleRankings(**slate)
        if epoch_id:
            self.cache_time = datetime.strptime(epoch_id, "%Y%m%d-%H%M").replace(
                tzinfo=timezone.utc
            )
        self._cache = new_cache

    def get(
        self,
        region: str | None = None,
        utcOffset: str | None = None,
    ) -> ContextualArticleRankings | None:
        """Fetch the recommendations based on region and utc offset"""
        keys = self._generate_cache_keys(region, utcOffset)
        # Probe in order of specificity
        ro = keys["region_offset"]
        if ro and ro in self._cache:
            return self._cache[ro]
        r = keys["region"]
        if r and r in self._cache:
            return self._cache[r]
        return self._cache.get(GLOBAL_KEY)

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
        )

    @property
    def update_count(self) -> int:
        """Return the number of times the ml data has been updated."""
        return self.synced_blob.update_count
