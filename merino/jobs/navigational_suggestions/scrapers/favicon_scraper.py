"""Favicon scraper for extracting favicon information from websites"""

import logging
from typing import Any, Optional

from merino.jobs.navigational_suggestions.constants import (
    LINK_SELECTOR,
    META_SELECTOR,
    MANIFEST_SELECTOR,
)
from merino.jobs.navigational_suggestions.models import FaviconData
from merino.jobs.navigational_suggestions.utils import join_url
from merino.jobs.navigational_suggestions.io import AsyncFaviconDownloader

logger = logging.getLogger(__name__)


class FaviconScraper:
    """Scraper for extracting favicon URLs from link tags, meta tags, and manifests."""

    def __init__(self, async_downloader: Optional[AsyncFaviconDownloader] = None) -> None:
        self.async_downloader = async_downloader or AsyncFaviconDownloader()

    def scrape_favicon_data(self, page) -> FaviconData:
        """Extract favicon references from link tags, meta tags, and manifest links."""
        try:
            links = [link.attrs for link in page.select(LINK_SELECTOR)]
            metas = [meta.attrs for meta in page.select(META_SELECTOR)]
            manifests = [manifest.attrs for manifest in page.select(f"head {MANIFEST_SELECTOR}")]

            return FaviconData(
                links=links,
                metas=metas,
                manifests=manifests,
            )
        except Exception as e:
            logger.warning(f"Error scraping favicon data: {e}")
            return FaviconData(links=[], metas=[], manifests=[])

    async def scrape_favicons_from_manifest(self, manifest_url: str) -> list[dict[str, Any]]:
        """Download manifest JSON and extract icons array."""
        result = []
        try:
            response = await self.async_downloader.requests_get(manifest_url)
            if response:
                try:
                    json_data = response.json()
                    result = json_data.get("icons", [])
                except (AttributeError, ValueError):
                    logger.debug(f"Failed to parse manifest JSON from {manifest_url}")
        except Exception as e:
            logger.debug(f"Exception getting manifest from {manifest_url}: {e}")
        return result

    async def get_default_favicon(self, base_url: str) -> Optional[str]:
        """Check if favicon.ico exists at domain root."""
        default_favicon_url: str = join_url(base_url, "favicon.ico")
        try:
            response = await self.async_downloader.requests_get(default_favicon_url)
            return str(response.url) if response else None
        except Exception as e:
            logger.debug(f"Exception getting default favicon from {base_url}: {e}")
            return None
