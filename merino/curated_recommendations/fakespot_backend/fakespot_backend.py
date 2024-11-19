"""Wrapper for Fakespot products data from Google Cloud Storage."""

import json
import logging
from typing import cast
from merino.curated_recommendations.fakespot_backend.protocol import (
    FakespotFeed,
    FakespotBackend,
    FakespotProduct,
    FAKESPOT_DEFAULT_CATEGORY_NAME,
    FAKESPOT_HEADER_COPY,
    FAKESPOT_FOOTER_COPY,
    FakespotCTA,
    FAKESPOT_CTA_COPY,
    FAKESPOT_CTA_URL,
    FAKESPOT_CACHE_KEY,
)
from aiodogstatsd import Client as StatsdClient
from merino.utils.synced_gcs_blob import SyncedGcsBlob

logger = logging.getLogger(__name__)

FakespotCacheType = dict[str, FakespotFeed]


class GcsFakespot(FakespotBackend):
    """Backend that caches and periodically retrieves fakespot products data from Google Cloud Storage."""

    def __init__(
        self,
        synced_gcs_blob: SyncedGcsBlob,
        metrics_client: StatsdClient,
        metrics_namespace: str,
    ) -> None:
        """Initialize the GcsFakespot backend.

        Args:
            synced_gcs_blob: Instance of SyncedGcsBlob that manages GCS synchronization.
        """
        self._cache: FakespotCacheType = {}
        self.synced_blob = synced_gcs_blob
        self.synced_blob.set_fetch_callback(self._fetch_callback)
        self.metrics_client = metrics_client
        self.metrics_namespace = metrics_namespace

    def get(self, key: str) -> FakespotFeed | None:
        """Get cached fakespot_feed

        Returns:
            FakespotFeed or None
        """
        return self._cache.get(key)

    @property
    def update_count(self) -> int:
        """Return the number of times the fakespot products data has been updated."""
        return self.synced_blob.update_count

    def _fetch_callback(self, data: str) -> None:
        """Process the raw fakespot products JSON blob data and update the cache.

        Args:
            data: The fakespot products blob string data, with an array of Fakespot products objects.
        """
        parsed_fakespot_products = [item for item in json.loads(data)]
        fakespot_products = []
        for product in parsed_fakespot_products:
            fakespot_products.append(
                FakespotProduct(
                    id=product["id"],
                    title=product["title"],
                    category=product["category"],
                    imageUrl=product["imageUrl"],
                    url=product["url"],
                )
            )
        fakespot_feed = FakespotFeed(
            products=fakespot_products,
            defaultCategoryName=FAKESPOT_DEFAULT_CATEGORY_NAME,
            headerCopy=FAKESPOT_HEADER_COPY,
            footerCopy=FAKESPOT_FOOTER_COPY,
            cta=FakespotCTA(ctaCopy=FAKESPOT_CTA_COPY, url=FAKESPOT_CTA_URL),
        )
        self._cache = {FAKESPOT_CACHE_KEY: fakespot_feed}
        self._track_metrics(FAKESPOT_CACHE_KEY)

    def _track_metrics(self, cache_key: str) -> None:
        """Emit statistics about fakespot products"""
        # Emit the total number of fakespot products
        fakespot_products_count = len(cast(FakespotFeed, self._cache.get(cache_key)).products)
        if fakespot_products_count:
            self.metrics_client.gauge(
                f"{self.metrics_namespace}.count", value=fakespot_products_count
            )
