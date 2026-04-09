"""Logos integration."""

import logging
from enum import StrEnum
from typing import Optional

import aiodogstatsd
from pydantic import HttpUrl
from gcloud.aio.storage import Bucket, Storage

from merino.configs import settings

logger = logging.getLogger(__name__)

STORAGE_BASE_URL = "https://storage.googleapis.com"


class LogoCategory(StrEnum):
    """Enumeration of logo categories available in GCS."""

    Airline = "airline"
    MLB = "mlb"
    NBA = "nba"
    NFL = "nfl"
    NHL = "nhl"


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
    metrics_namespace = "manifest"
    provider_name = "logos"
    blob_prefix = "logos"
    storage_base_url = STORAGE_BASE_URL

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        storage_client: Storage,
        enabled_by_default: bool = False,
    ) -> None:
        bucket = settings.image_gcs_v2.gcs_bucket
        self._metrics_client = metrics_client
        self._enabled_by_default = enabled_by_default
        self._storage_client = storage_client
        self._bucket = Bucket(storage=storage_client, name=bucket)
        super().__init__()

    async def get_logo_url(self, category: LogoCategory, key: str) -> Optional[HttpUrl]:
        """Get a logo URL for a given category and lookup key.

        This is knowingly brittle, but since the logo upload process is
        entirely manual (and therefore not linked to existing data models),
        it's not worth introducing additional complexity or validation at
        this time. We rely on uploaders to adhere to the expected contract.

        If a logo cannot be found for the category and key, increments
        a miss metric and logs a warning so the team can debug real gaps vs.
        mistaken lookups.
        """
        blob_name = f"{self.blob_prefix}/{category}/{category}_{key.lower()}.png"
        exists = await self._bucket.blob_exists(blob_name)
        if not exists:
            logger.warning(f"Failed to find a logo for category={category} and key={key}")
            self._metrics_client.increment(
                "gcs.blob.fetch", tags={"provider": self.provider_name, "result": "not_found"}
            )
            return None
        else:
            self._metrics_client.increment(
                "gcs.blob.fetch", tags={"provider": self.provider_name, "result": "found"}
            )
        return HttpUrl(f"{self.storage_base_url}/{blob_name}")
