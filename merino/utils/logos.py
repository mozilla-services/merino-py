"""Logos utility"""

import logging
from datetime import datetime
from enum import StrEnum
from functools import cache
from typing import Optional
import orjson
from importlib.resources import files
from urllib.parse import urljoin

from pydantic import BaseModel, HttpUrl

from merino.utils.metrics import get_metrics_client
from merino.configs import settings

logger = logging.getLogger(__name__)
metrics_client = get_metrics_client()


_cdn_host_name: str = settings.image_gcs_v2.cdn_hostname
_protocol = "http" if "localhost" in _cdn_host_name else "https"
CDN_ROOT_URL: str = f"{_protocol}://{_cdn_host_name}"


class LogoCategory(StrEnum):
    """Enumeration of logo categories available in GCS."""

    Airline = "airline"
    MLB = "mlb"
    NBA = "nba"
    NFL = "nfl"
    NHL = "nhl"


class Logo(BaseModel):
    """A single lookup entry from the lookup manifest."""

    name: str
    url: str


class LogoManifest(BaseModel):
    """Manifest mapping logo categories and keys to logo metadata."""

    generated_at: datetime
    lookups: dict[LogoCategory, dict[str, Logo]]

    def get(self, category: LogoCategory, key: str) -> Logo | None:
        """Return the LookupEntry for a given category and key, or None if not found."""
        return self.lookups.get(category, {}).get(key.upper())


@cache
def load_manifest() -> LogoManifest:
    """Load manifest and cache in memory"""
    manifest_path = files("merino.data") / "logos_manifest.json"
    return LogoManifest.model_validate(orjson.loads(manifest_path.read_bytes()))


def get_logo_url(category: LogoCategory, key: str) -> Optional[HttpUrl]:
    """Logo lookup for suggest providers.

    The process for creating suggestions is currently manual,
    and must follow the LogoManifest schema.

    Each category dict is comprised of lookup keys to identify
    a particular entity in the category.
    For airlines, that is the 2-letter IATA code (lowercased).
    For sports teams, it corresponds to the "key" field in the
    `merino.providers.suggest.sports.backends.sportsdata.common.Team`
    model.
    """
    logo = load_manifest().get(category, key)
    if logo is None:
        logger.warning(f"Logo does not exist for category={category} and key={key}")
        # Normalize to the manifest's uppercase storage form so "aa" and "AA"
        # collapse to a single series. Cardinality is bounded by the known key
        # spaces (IATA codes, sports team keys), so this is safe for Prometheus.
        metrics_client.increment(
            "manifest.lookup",
            tags={"name": f"logos.{category}", "key": key.upper(), "result": "miss"},
        )
        return None
    return HttpUrl(urljoin(CDN_ROOT_URL, logo.url))
