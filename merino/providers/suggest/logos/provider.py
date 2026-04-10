"""Logos integration."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Optional

import aiodogstatsd
from pydantic import HttpUrl, BaseModel

from merino.utils.synced_gcs_blob_v2 import SyncedGcsBlobV2

logger = logging.getLogger(__name__)

STORAGE_BASE_URL = "https://storage.googleapis.com"


class LogoCategory(StrEnum):
    """Enumeration of logo categories available in GCS."""

    Airline = "airline"
    MLB = "mlb"
    NBA = "nba"
    NFL = "nfl"
    NHL = "nhl"


class Logo(BaseModel):
    """A logo."""

    url: HttpUrl
    format: str  # e.g. "png"


class LogoEntry(BaseModel):
    """A single lookup entry from the lookup manifest."""

    name: str
    abbreviation: str
    logo: Logo


class LogoManifest(BaseModel):
    """Manifest mapping logo categories and keys to logo metadata."""

    generated_at: datetime
    lookups: dict[LogoCategory, dict[str, LogoEntry]]

    def get(self, category: LogoCategory, key: str) -> LogoEntry | None:
        """Return the LookupEntry for a given category and key, or None if not found."""
        return self.lookups.get(category, {}).get(key.upper())


class Provider:
    """Suggestion provider for Logos.

    The process for creating suggestions is currently manual.
    All icon names must adhere to the following name contract:

    "/logos/{category}/{category}_{key}.png" (all lowercased)

    where category is enumerated in LogoCategory, e.g. "airline", "mlb"
    and the key is the unique lookup key. For airlines, that is the 2-letter
    IATA code (lowercased). For sports teams, it corresponds to
    the "key" field in merino.providers.suggest.sports.backends.sportsdata.common.Team
    model.
    """

    url = HttpUrl("https://merino.services.mozilla.com/")
    # TODO: Where should this be to be reused...
    metrics_namespace = "manifest"
    provider_name = "logos"
    storage_base_url = STORAGE_BASE_URL

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        logo_manifest: SyncedGcsBlobV2[LogoManifest],
    ) -> None:
        self._metrics_client = metrics_client
        self._logo_manifest = logo_manifest
        super().__init__()

    def initialize(self):
        """Initialize the provider and dependencies."""
        self._logo_manifest.initialize()

    async def get_logo_url(self, category: LogoCategory, key: str) -> Optional[HttpUrl]:
        """Get a logo URL for a given category and lookup key."""
        logo_manifest = self._logo_manifest.data
        if logo_manifest is None:
            return None
        logo_data = logo_manifest.get(category, key)
        if logo_data is None:
            logger.warning(f"Logo does not exist for category={category} and key={key}")
            self._metrics_client.increment(
                f"{self.metrics_namespace}.lookup.miss", tags={"provider": self.provider_name}
            )
            return None
        return logo_data.logo.url
