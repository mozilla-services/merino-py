"""Favicon extractor for extracting favicon URLs from websites"""

import logging
from typing import Any, Optional
from bs4 import BeautifulSoup

from merino.jobs.navigational_suggestions.constants import DEFAULT_MAX_FAVICON_ICONS
from merino.jobs.navigational_suggestions.models import FaviconData
from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import FaviconScraper
from merino.jobs.navigational_suggestions.utils import join_url, process_favicon_url

logger = logging.getLogger(__name__)


class FaviconExtractor:
    """Extract favicon URLs from link tags, meta tags, manifests, and default location."""

    def __init__(self, favicon_scraper: FaviconScraper) -> None:
        self.favicon_scraper = favicon_scraper

    async def extract_favicons(
        self,
        page: Optional[BeautifulSoup],
        scraped_url: str,
        max_icons: int = DEFAULT_MAX_FAVICON_ICONS,
    ) -> list[dict[str, Any]]:
        """Extract up to max_icons favicons, stopping early if limit reached."""
        favicons: list[dict[str, Any]] = []

        try:
            # Get all favicon data from the page
            favicon_data: FaviconData = self.favicon_scraper.scrape_favicon_data(page)

            # Priority 1: Process standard link icons (usually higher quality)
            favicons = self._process_link_favicons(favicon_data.links, scraped_url, max_icons)
            if len(favicons) >= max_icons:
                return favicons

            # Priority 2: Process meta tags if we still need more
            remaining_slots = max_icons - len(favicons)
            meta_favicons = self._process_meta_favicons(
                favicon_data.metas, scraped_url, remaining_slots
            )
            favicons.extend(meta_favicons)
            if len(favicons) >= max_icons:
                return favicons

            # Priority 3: Try default favicon.ico if still below max
            if len(favicons) < max_icons:
                default_favicon = await self._process_default_favicon(scraped_url)
                if default_favicon:
                    favicons.append(default_favicon)

            # Priority 4: Only process manifests if we still need more icons
            if len(favicons) < max_icons and favicon_data.manifests:
                remaining_slots = max_icons - len(favicons)
                manifest_favicons = await self._process_manifest_favicons(
                    favicon_data.manifests, scraped_url, remaining_slots
                )
                favicons.extend(manifest_favicons)

        except Exception as e:
            logger.error(f"Exception extracting favicons: {e}")

        return favicons

    def _process_link_favicons(
        self, links: list[dict[str, Any]], base_url: str, max_icons: int
    ) -> list[dict[str, Any]]:
        """Process favicons from link tags."""
        favicons = []

        for link in links[:max_icons]:
            favicon_url = link.get("href", "")

            # Process URL using common pattern
            processed_favicon = process_favicon_url(favicon_url, base_url, "link")
            if processed_favicon is None:
                continue

            # Update link with processed data and preserve other attributes
            link.update(processed_favicon)
            favicons.append(link)

            # Early stopping if we've reached our limit
            if len(favicons) >= max_icons:
                break

        return favicons

    def _process_meta_favicons(
        self, metas: list[dict[str, Any]], base_url: str, max_icons: int
    ) -> list[dict[str, Any]]:
        """Process favicons from meta tags."""
        favicons = []

        for meta in metas[:max_icons]:
            favicon_url = meta.get("content", "")

            # Process URL using common pattern
            processed_favicon = process_favicon_url(favicon_url, base_url, "meta")
            if processed_favicon is None:
                continue

            # Update meta with processed data and preserve other attributes
            meta.update(processed_favicon)
            favicons.append(meta)

            # Early stopping if we've reached our limit
            if len(favicons) >= max_icons:
                break

        return favicons

    async def _process_default_favicon(self, base_url: str) -> dict[str, Any] | None:
        """Check for favicon.ico at site root."""
        try:
            default_favicon_url = await self.favicon_scraper.get_default_favicon(base_url)
            if default_favicon_url:
                return {"href": default_favicon_url, "_source": "default"}
        except Exception as e:
            logger.debug(f"Error getting default favicon: {e}")

        return None

    async def _process_manifest_favicons(
        self, manifests: list[dict[str, Any]], base_url: str, max_icons: int
    ) -> list[dict[str, Any]]:
        """Process favicons from first manifest only."""
        favicons: list[dict[str, Any]] = []

        if not manifests:
            return favicons

        # Only process first manifest to limit resource usage
        first_manifest = manifests[0]
        manifest_url: str = str(first_manifest.get("href", ""))

        if not manifest_url:
            return favicons

        manifest_absolute_url: str = join_url(base_url, manifest_url)

        try:
            manifest_icons = await self.favicon_scraper.scrape_favicons_from_manifest(
                manifest_absolute_url
            )

            # Add icons from manifest up to our limit
            for scraped_favicon in manifest_icons[:max_icons]:
                favicon_src = scraped_favicon.get("src", "")

                # Process URL using common pattern
                processed_favicon = process_favicon_url(
                    favicon_src, manifest_absolute_url, "manifest"
                )
                if processed_favicon is None:
                    continue

                favicons.append(processed_favicon)

                # Check if we've reached our limit
                if len(favicons) >= max_icons:
                    break

        except Exception as e:
            logger.warning(f"Error processing manifest: {e}")

        return favicons
