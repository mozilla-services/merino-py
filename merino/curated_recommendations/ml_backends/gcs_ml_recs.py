"""Module dedicated to backends for Thompson sampling priors loaded from GCS."""

import json
import logging

from merino.curated_recommendations.ml_backends.protocol import (
    MLRecsBackend,
    ContextualArticleRankings,
    ContextualArticleRanked,
    ContextualArticlesBySample,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

GLOBAL_KEY = "global"


class GcsMLRecs(MLRecsBackend):
    """Backend that fetches ML Recs from GCS for Contextual Ranker"""

    def __init__(self, synced_gcs_blob: SyncedGcsBlob) -> None:
        self._cache: dict[str, ContextualArticleRankings] = {}  # string keys only
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)

    @staticmethod
    def _generate_cache_keys(region: str | None, utc_offset: str | None) -> dict[str, str]:
        """Never return Nones; normalize to strings."""
        r = (region or "").strip().upper()
        o = (utc_offset or "").strip()
        return {
            "region_offset": f"{r}_{o}" if (r or o) else GLOBAL_KEY,
            "region": r,
            "global": GLOBAL_KEY,
        }

    def _fetch_callback(self, data: bytes | str) -> None:
        """Process the raw blob data and update the cache atomically."""
        payload = json.loads(data if isinstance(data, str) else data.decode("utf-8"))
        k = int(payload.get("K", 10))
        slates = payload.get("slates") or {}

        new_cache: dict[str, ContextualArticleRankings] = {}
        for region_offset, slate in slates.items():
            shards = (slate or {}).get("shards") or {}
            article_by_sample: dict[str, ContextualArticlesBySample] = {}
            for sample, rows in shards.items():  # sample like "0", "1", ...
                s = str(sample)
                article_by_sample[s] = ContextualArticlesBySample(
                    sample=s,
                    articles=[ContextualArticleRanked(**row) for row in rows],
                )
            key = str(region_offset)
            new_cache[key] = ContextualArticleRankings(
                region_offset=key,
                articles_by_sample=article_by_sample,
                n_samples=k,
            )

        self._cache = new_cache

    def get(
        self,
        region: str | None = None,
        utc_offset: str | None = None,
    ) -> ContextualArticleRankings | None:
        """Fetch the recommendations based on region and utc offset"""
        keys = self._generate_cache_keys(region, utc_offset)
        # Probe in order of specificity
        ro = keys["region_offset"]
        if ro and ro in self._cache:
            return self._cache[ro]
        r = keys["region"]
        if r and r in self._cache:
            return self._cache[r]
        return self._cache.get(GLOBAL_KEY)

    @property
    def update_count(self) -> int:
        """Return the number of times the prior data has been updated."""
        return self.synced_blob.update_count
