"""Extract domain metadata from domain data"""

import asyncio
import itertools
import logging
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel
from robobrowser import RoboBrowser

from merino.jobs.navigational_suggestions.domain_metadata_uploader import DomainMetadataUploader
from merino.utils.gcs.models import Image
from merino.jobs.navigational_suggestions.utils import (
    REQUEST_HEADERS,
    TIMEOUT,
    AsyncFaviconDownloader,
)

logger = logging.getLogger(__name__)


class FaviconData(BaseModel):
    """Data model for favicon information extracted from a website."""

    links: list[dict[str, Any]]
    metas: list[dict[str, Any]]
    manifests: list[dict[str, Any]]


class Scraper:
    """Website data extractor."""

    LINK_SELECTOR: str = (
        "link[rel=apple-touch-icon], link[rel=apple-touch-icon-precomposed],"
        'link[rel="icon shortcut"], link[rel="shortcut icon"], link[rel="icon"],'
        'link[rel="SHORTCUT ICON"], link[rel="fluid-icon"], link[rel="mask-icon"],'
        'link[rel="apple-touch-startup-image"]'
    )
    META_SELECTOR: str = "meta[name=apple-touch-icon], meta[name=msapplication-TileImage]"
    MANIFEST_SELECTOR: str = 'link[rel="manifest"]'

    browser: RoboBrowser
    request_client: AsyncFaviconDownloader

    def __init__(self) -> None:
        session: requests.Session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        self.browser = RoboBrowser(session=session, parser="html.parser", allow_redirects=True)
        self.request_client = AsyncFaviconDownloader()

    def open(self, url: str) -> Optional[str]:
        """Open the given url for scraping.

        Args:
            url: URL to open
        Returns:
            Optional[str]: Full URL that was opened
        """
        try:
            self.browser.open(url, timeout=TIMEOUT)
            return str(self.browser.url)
        except Exception:
            return None

    def scrape_favicon_data(self) -> FaviconData:
        """Scrape the favicon data for an already opened URL.

        Returns:
            FaviconData: Favicon data for a URL
        """
        return FaviconData(
            links=[link.attrs for link in self.browser.select(self.LINK_SELECTOR)],
            metas=[meta.attrs for meta in self.browser.select(self.META_SELECTOR)],
            manifests=[
                manifest.attrs
                for manifest in self.browser.select(f"head {self.MANIFEST_SELECTOR}")
            ],
        )

    async def scrape_favicons_from_manifest(self, manifest_url: str) -> list[dict[str, Any]]:
        """Scrape favicons from manifest of an already opened URL asynchronously.

        Args:
            manifest_url: URL of the manifest file
        Returns:
            list[str]: URLs of the scraped favicons
        """
        result = []
        try:
            response = await self.request_client.requests_get(manifest_url)
            if response:
                try:
                    json_data = response.json()
                    result = json_data.get("icons", [])
                except (AttributeError, ValueError):
                    logger.debug(f"Failed to parse manifest JSON from {manifest_url}")
        except Exception as e:
            logger.debug(f"Exception getting manifest from {manifest_url}: {e}")
        return result

    async def get_default_favicon(self, url: str) -> Optional[str]:
        """Return the default favicon for the given url asynchronously.

        Args:
            url: URL to scrape for favicon at default location
        Returns:
            Optional[str]: Default favicon url if it exists
        """
        try:
            default_favicon_url: str = urljoin(url, "favicon.ico")
            response = await self.request_client.requests_get(default_favicon_url)
            return str(response.url) if response else None
        except Exception:
            return None

    def scrape_title(self) -> Optional[str]:
        """Scrape the title from the header of an already opened url.

        Returns:
            Optional[str]: The title extracted from header of a url
        """
        try:
            return str(self.browser.find("head").find("title").get_text())
        except Exception:
            return None


class DomainMetadataExtractor:
    """Extract domain metadata from domain data"""

    # A non-exhaustive list of substrings of invalid titles
    INVALID_TITLES = [
        "Attention Required",
        "Access denied",
        "Access Denied",
        "Access to this page has been denied",
        "Loading…",
        "Page loading",
        "Just a moment...",
        "Site Maintenance",
        "502 Bad Gateway",
        "503 Service Temporarily Unavailable",
        "Your request has been blocked",
        "This page is either unavailable or restricted",
        "Let's Get Your Identity Verified",
        "Your Access To This Website Has Been Blocked",
        "Error",
        "This page is not allowed",
        "Robot or human",
        "Captcha Challenge",
        "Let us know you're not a robot",
        "Verification",
        "404",
        "Please try again",
        "Access to this page",
        "We'll be right back",
        "Bot or Not?",
        "Too Many Requests",
        "IP blocked",
        "Service unavailable",
    ]

    # Constants for favicon URL validation
    MANIFEST_JSON_BASE64_MARKER = "/application/manifest+json;base64,"

    # List of blocked (second level) domains
    blocked_domains: set[str]
    scraper: Scraper
    favicon_downloader: AsyncFaviconDownloader

    def __init__(
        self,
        blocked_domains: set[str],
        scraper: Scraper = Scraper(),
        favicon_downloader: AsyncFaviconDownloader = AsyncFaviconDownloader(),
    ) -> None:
        self.scraper = scraper
        self.favicon_downloader = favicon_downloader
        self.blocked_domains = blocked_domains

    def _get_base_url(self, url: str) -> str:
        """Return base url from a given full url"""
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.hostname}"

    def _fix_url(self, url: str) -> str:
        # Skip empty URLs or single slash
        if not url or url == "/":
            return ""

        # Handle protocol-relative URLs
        if url.startswith("//"):
            return f"https:{url}"
        # Handle URLs without protocol
        elif not url.startswith(("http://", "https://")) and not url.startswith("/"):
            return f"https://{url}"
        # Handle absolute paths with base URL context
        elif not url.startswith(("http://", "https://")) and url.startswith("/"):
            # We need real URL joining here, not string concatenation
            if hasattr(self, "_current_base_url") and self._current_base_url:
                return urljoin(self._current_base_url, url)
            else:
                return ""
        # Return unchanged URLs that already have a protocol
        return url

    def _get_favicon_smallest_dimension(self, image: Image) -> int:
        """Return the smallest of the favicon image width and height"""
        width, height = image.open().size
        return int(min(width, height))

    async def _extract_favicons(
        self, scraped_url: str, max_icons: int = 5
    ) -> list[dict[str, Any]]:
        """Extract a limited number of favicons for an already opened url"""
        self._current_base_url = scraped_url
        favicons: list[dict[str, Any]] = []

        try:
            # Get the most common favicon sources first
            favicon_data: FaviconData = self.scraper.scrape_favicon_data()

            # First priority: process standard link icons (usually higher quality)
            for favicon in favicon_data.links[:max_icons]:
                favicon_url = favicon["href"]
                if self._is_problematic_favicon_url(favicon_url):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith("//"):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                favicons.append(favicon)

                # Early stopping if we've reached our limit
                if len(favicons) >= max_icons:
                    return favicons

            # If we still need more, try meta tags next
            remaining_slots = max_icons - len(favicons)
            for favicon in favicon_data.metas[:remaining_slots]:
                favicon_url = favicon["content"]
                if self._is_problematic_favicon_url(favicon_url):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith("//"):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                else:
                    favicon["href"] = favicon_url
                favicons.append(favicon)

                # Check if we've reached our limit
                if len(favicons) >= max_icons:
                    return favicons

            # If still below max, try the default favicon
            if len(favicons) < max_icons:
                default_favicon_url = await self.scraper.get_default_favicon(scraped_url)
                if default_favicon_url is not None:
                    favicons.append({"href": default_favicon_url})

                    # Check if we've reached our limit
                    if len(favicons) >= max_icons:
                        return favicons

            # Only process manifests if we still need more icons
            if len(favicons) < max_icons and favicon_data.manifests:
                remaining_slots = max_icons - len(favicons)

                # Only process first manifest to limit resource usage
                first_manifest = favicon_data.manifests[0]
                manifest_url: str = str(first_manifest.get("href"))
                manifest_absolute_url: str = urljoin(scraped_url, manifest_url)

                try:
                    manifest_icons = await self.scraper.scrape_favicons_from_manifest(
                        manifest_absolute_url
                    )

                    # Add icons from manifest up to our remaining limit
                    for i, scraped_favicon in enumerate(manifest_icons[:remaining_slots]):
                        favicon_src = scraped_favicon.get("src", "")

                        if self._is_problematic_favicon_url(favicon_src):
                            continue

                        if favicon_src.startswith(("http://", "https://")):
                            favicon_url = favicon_src
                        else:
                            favicon_url = urljoin(manifest_absolute_url, favicon_src)

                        favicons.append({"href": favicon_url})

                        # Check if we've reached our limit
                        if len(favicons) >= max_icons:
                            break

                except Exception as e:
                    logger.warning(f"Error processing manifest: {e}")

        except Exception as e:
            logger.error(f"Exception extracting favicons: {e}")

        return favicons

    async def _process_favicon(
        self, scraped_url: str, min_width: int, uploader: "DomainMetadataUploader"
    ) -> str:
        """Extract all favicons for an already opened URL and return the one that satisfies the
        minimum width criteria. If multiple favicons satisfy the criteria then upload the one
        with the highest resolution and return the url.
        """
        # Extract favicon candidates (with a reasonable limit)
        favicons = await self._extract_favicons(scraped_url, max_icons=5)

        # Use the optimized method to handle favicons
        return await self._upload_best_favicon(favicons, min_width, uploader)

    async def _upload_best_favicon(
        self, favicons: list[dict[str, Any]], min_width: int, uploader: DomainMetadataUploader
    ) -> str:
        """Asynchronous method to find the best favicon"""
        # Get URLs and filter out empty or problematic ones
        urls = [self._fix_url(favicon.get("href", "")) for favicon in favicons]
        # Remove empty strings and any remaining problematic URLs
        urls = [url for url in urls if url and "://" in url]

        # If we have no valid URLs after filtering, return empty string
        if not urls:
            return ""

        masked_svg_indices = [i for i, favicon in enumerate(favicons) if "mask" in favicon]

        best_favicon_url = ""
        best_favicon_width = 0

        # Process favicons in smaller chunks to limit concurrent connections and memory usage
        chunk_size = 5

        for chunk_idx, chunk_urls in enumerate(itertools.batched(urls, chunk_size)):
            chunk_images = await self.favicon_downloader.download_multiple_favicons(
                list(chunk_urls)
            )

            # Calculate the offset in the favicons list for this chunk
            favicon_offset = chunk_idx * chunk_size

            # Process this chunk immediately
            for i, (image, url) in enumerate(zip(chunk_images, chunk_urls)):
                if image is None or "image/" not in image.content_type:
                    del image
                    continue

                # First priority: If favicon is an SVG and not masked, select it immediately
                if (
                    image.content_type == "image/svg+xml"
                    and (i + favicon_offset) not in masked_svg_indices
                ):
                    # Upload and return immediately on finding a good SVG
                    try:
                        dst_favicon_name = uploader.destination_favicon_name(image)
                        result = uploader.upload_image(image, dst_favicon_name, forced_upload=True)
                        # Clear variables to help with garbage collection
                        del chunk_images
                        return str(result)
                    except Exception as e:
                        logger.warning(f"Failed to upload SVG favicon: {e}")
                        return url

                # Second priority: Track the highest resolution bitmap favicon
                try:
                    width = self._get_favicon_smallest_dimension(image)
                    if width > best_favicon_width:
                        try:
                            # Upload immediately
                            dst_favicon_name = uploader.destination_favicon_name(image)
                            favicon_url = uploader.upload_image(
                                image, dst_favicon_name, forced_upload=True
                            )
                            best_favicon_url = favicon_url
                            best_favicon_width = width
                        except Exception as e:
                            logger.warning(f"Failed to upload bitmap favicon: {e}")
                            best_favicon_url = url
                            best_favicon_width = width
                except Exception:
                    logger.warning(f"Exception for favicon at position {i+favicon_offset}")

            # Explicitly clear chunk_images to free memory immediately
            del chunk_images

            # Add a longer delay between batches to prevent network resource exhaustion
            await asyncio.sleep(1.0)

        return best_favicon_url if best_favicon_width >= min_width else ""

    def _extract_title(self) -> Optional[str]:
        """Extract title for a url"""
        title: Optional[str] = self.scraper.scrape_title()
        if title:
            title = " ".join(title.split())
            title = (
                title
                if title
                and not [t for t in self.INVALID_TITLES if t.casefold() in title.casefold()]
                else None
            )
        return title

    def _get_title(self, fallback_title: str) -> str:
        """Extract title for a url. If not present then return the fallback title"""
        return self._extract_title() or fallback_title.capitalize()

    def _get_second_level_domain(self, domain: str, top_level_domain: str) -> str:
        """Extract the second level domain from domain name and suffix"""
        return domain.replace("." + top_level_domain, "")

    def _is_domain_blocked(self, domain: str, suffix: str) -> bool:
        """Check if a domain is in the blocked list"""
        second_level_domain: str = self._get_second_level_domain(domain, suffix)
        return second_level_domain in self.blocked_domains

    def _is_problematic_favicon_url(self, favicon_url: str) -> bool:
        """Check if a favicon URL is problematic (data URL or base64 manifest)"""
        return favicon_url.startswith("data:") or self.MANIFEST_JSON_BASE64_MARKER in favicon_url

    def process_domain_metadata(
        self,
        domains_data: list[dict[str, Any]],
        favicon_min_width: int,
        uploader: DomainMetadataUploader,
    ) -> list[dict[str, Optional[str]]]:
        """Extract domain metadata for each domain, processing all concurrently and upload the
        favicons directly to the Google Cloud bucket
        """
        logger.info(f"Starting to process {len(domains_data)} domains")
        results = asyncio.run(self._process_domains(domains_data, favicon_min_width, uploader))
        successful_domains = sum(1 for result in results if result.get("icon"))
        logger.info(
            f"Completed processing: {len(results)} domains, found favicons for {successful_domains}"
        )
        return results

    async def _process_domains(
        self,
        domains_data: list[dict[str, Any]],
        favicon_min_width: int,
        uploader: DomainMetadataUploader,
    ) -> list[dict[str, Optional[str]]]:
        """Process domains in chunks to limit resource consumption."""
        # Reduce batch size to decrease memory consumption and network load
        chunk_size = 10
        filtered_results: list[dict[str, Optional[str]]] = []
        total_chunks = (len(domains_data) + chunk_size - 1) // chunk_size

        for i in range(0, len(domains_data), chunk_size):
            end_idx = min(i + chunk_size, len(domains_data))
            chunk = domains_data[i:end_idx]
            chunk_num = i // chunk_size + 1

            logger.info(
                f"Processing chunk {chunk_num}/{total_chunks} ({i+1}-{end_idx} of {len(domains_data)})"
            )

            tasks = [
                self._process_single_domain(domain_data, favicon_min_width, uploader)
                for domain_data in chunk
            ]

            # Process current chunk with gather
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Add a longer delay between chunks to allow system resources to recover
            if end_idx < len(domains_data):
                await asyncio.sleep(2.0)

            # Process results
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Error processing domain: {result}")
                else:
                    if not isinstance(result, dict):
                        logger.error(f"Unexpected result type: {result}")
                        continue
                    filtered_results.append(result)

        return filtered_results

    async def _process_single_domain(
        self, domain_data: dict[str, Any], favicon_min_width: int, uploader: DomainMetadataUploader
    ) -> dict[str, Optional[str]]:
        """Process a single domain asynchronously and always return a valid dict."""
        try:
            scraped_base_url: Optional[str] = None
            favicon: str = ""
            title: str = ""
            second_level_domain: str = ""

            domain: str = domain_data["domain"]
            suffix: str = domain_data["suffix"]

            if not self._is_domain_blocked(domain, suffix):
                url: str = f"https://{domain}"
                full_url: Optional[str] = self.scraper.open(url)

                if full_url is None:
                    # Retry with www. in the url as some domains require it explicitly
                    url = f"https://www.{domain}"
                    full_url = self.scraper.open(url)

                if full_url and domain in full_url:
                    scraped_base_url = self._get_base_url(full_url)
                    favicon = await self._process_favicon(
                        scraped_base_url, favicon_min_width, uploader
                    )
                    second_level_domain = self._get_second_level_domain(domain, suffix)
                    title = self._get_title(second_level_domain)

                    if favicon:
                        logger.info(f"Found favicon for domain: {domain}")

            return {
                "url": scraped_base_url,
                "title": title,
                "icon": favicon,
                "domain": second_level_domain,
            }
        except Exception:
            # Return a default dict in case of error.
            return {"url": None, "title": None, "icon": None, "domain": None}
