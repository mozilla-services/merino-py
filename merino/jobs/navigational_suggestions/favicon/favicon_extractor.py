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
            has_link_icons = len(favicons) > 0
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

            # Priority 3: Try conventional /apple-touch-icon.png path
            # Many sites serve a 180x180 icon here even without an HTML link
            if len(favicons) < max_icons:
                apple_touch = await self._process_apple_touch_icon_fallback(scraped_url)
                if apple_touch:
                    favicons.append(apple_touch)

            # Priority 4: Try default favicon.ico only if no link icons exist
            # This matches Firefox behavior: /favicon.ico is a fallback, not an
            # additional source when the page already declares icons via <link>.
            if len(favicons) < max_icons and not has_link_icons:
                default_favicon = await self._process_default_favicon(scraped_url)
                if default_favicon:
                    favicons.append(default_favicon)

            # Priority 5: Only process manifests if we still need more icons
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
        """Process favicons from link tags, sorted by Firefox's favicon priority.

        Firefox selects favicons by: SVG > apple-touch-icon > largest size > rest.
        We apply this sort before the max_icons limit so that the highest-quality
        icons aren't cut off by smaller ones appearing earlier in the document.

        Icons with a ``color`` attribute are skipped because they are Safari-specific
        mask icons and not used by Firefox.
        """
        favicons = []

        # Filter out Safari-specific icons with color attribute (Firefox skips these)
        filtered_links = [link for link in links if "color" not in link]

        sorted_links = sorted(filtered_links, key=self._link_priority_key)

        for link in sorted_links[:max_icons]:
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

    @staticmethod
    def _link_priority_key(link: dict[str, Any]) -> tuple[int, int]:
        """Sort key matching Firefox's favicon selection: SVG > apple-touch-icon > largest size.

        Returns a (priority_tier, sub_sort) tuple. Lower values sort first.
        ``priority_tier`` groups icons by type (0=SVG, 1=apple-touch-icon,
        2=sized bitmap, 3=everything else). ``sub_sort`` orders within a tier;
        for sized bitmaps it is the negative pixel width so larger icons win.
        """
        href = str(link.get("href", "")).lower()
        rel_values = link.get("rel", [])

        # Priority 0: SVG icons (scalable, always sharp)
        if href.endswith(".svg"):
            return (0, 0)

        # Priority 1: apple-touch-icon variants (typically 180x180)
        if any("apple-touch" in str(r) for r in rel_values):
            return (1, 0)

        # Priority 2: Icons with known sizes (larger first via negative width)
        sizes = str(link.get("sizes", ""))
        if sizes and "x" in sizes.lower():
            try:
                width = int(sizes.lower().split("x")[0])
                return (2, -width)
            except ValueError, IndexError:
                pass

        # Priority 3: Everything else
        return (3, 0)

    async def _process_apple_touch_icon_fallback(self, base_url: str) -> dict[str, Any] | None:
        """Try conventional /apple-touch-icon.png path (usually 180x180).

        Many sites serve an apple-touch-icon at this well-known path even if
        it is not linked in the HTML. This catches cases where the HTML only
        contains small favicon.ico references.
        """
        try:
            apple_touch_url = join_url(base_url, "/apple-touch-icon.png")
            response = await self.favicon_scraper.async_downloader.requests_get(apple_touch_url)
            if response and "image/" in response.headers.get("Content-Type", ""):
                return {"href": str(response.url), "_source": "link"}
        except Exception as e:
            logger.debug(f"Error getting apple-touch-icon fallback: {e}")
        return None

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
