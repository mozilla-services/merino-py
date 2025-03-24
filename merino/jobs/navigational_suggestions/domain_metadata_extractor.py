"""Extract domain metadata from domain data"""

import asyncio
import itertools
import logging
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel
from robobrowser import RoboBrowser
from typing import cast

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
        except Exception as e:
            logger.info(f"Exception: {e} while opening url {url}")
            return None

    def scrape_favicon_data(self, url: str) -> FaviconData:
        """Scrape the favicon data for an already opened URL.

        Args:
            url: URL to scrape for favicon data
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
                except AttributeError as e:
                    logger.warning(
                        f"Exception: {e} while parsing icons from manifest {manifest_url}"
                    )
                except ValueError as e:
                    logger.warning(
                        f"Exception: {e} while parsing JSON from manifest {manifest_url}"
                    )
        except Exception as e:
            logger.warning(f"Exception: {e} while parsing icons from manifest {manifest_url}")
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
        except AttributeError as e:
            logger.info(f"Exception: {e} while getting default favicon {default_favicon_url}")
            return None
        except Exception as e:
            logger.info(f"Exception: {e} while getting default favicon {default_favicon_url}")
            return None

    def scrape_title(self) -> Optional[str]:
        """Scrape the title from the header of an already opened url.

        Returns:
            Optional[str]: The title extracted from header of a url
        """
        try:
            return str(self.browser.find("head").find("title").get_text())
        except Exception as e:
            logger.info(f"Exception: {e} while scraping title")
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
        """Return a url with https scheme if the scheme is originally missing from it"""
        # Handle protocol-relative URLs (starting with //)
        if url.startswith("//"):
            return f"https:{url}"
        # Handle URLs without protocol but with domain name structure
        elif not url.startswith(("http://", "https://")) and not url.startswith("/"):
            return f"https://{url}"
        # Handle absolute paths without domain by keeping the format consistent
        # with how the calling code expects it
        elif not url.startswith(("http://", "https://")) and url.startswith("/"):
            return f"https:{url}"
        # Return unchanged URLs that already have a protocol
        return url

    def _get_favicon_smallest_dimension(self, image: Image) -> int:
        """Return the smallest of the favicon image width and height"""
        width, height = image.open().size
        return int(min(width, height))

    async def _extract_favicons(self, scraped_url: str) -> list[dict[str, Any]]:
        """Extract all favicons for an already opened url asynchronously"""
        logger.info(f"Extracting all favicons for {scraped_url}")
        favicons: list[dict[str, Any]] = []
        try:
            favicon_data: FaviconData = self.scraper.scrape_favicon_data(scraped_url)

            for favicon in favicon_data.links:
                favicon_url = favicon["href"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith("//"):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                favicons.append(favicon)

            for favicon in favicon_data.metas:
                favicon_url = favicon["content"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith("//"):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                else:
                    favicon["href"] = favicon_url
                favicons.append(favicon)

            # Process manifests concurrently
            manifest_tasks = []
            manifest_urls = []

            for manifest in favicon_data.manifests:
                manifest_url: str = str(manifest.get("href"))
                manifest_absolute_url: str = urljoin(scraped_url, manifest_url)
                manifest_tasks.append(
                    self.scraper.scrape_favicons_from_manifest(manifest_absolute_url)
                )
                manifest_urls.append(manifest_absolute_url)

            if manifest_tasks:
                # Use smaller chunk size for manifest tasks to limit resource usage
                chunk_size = 10
                for i in range(0, len(manifest_tasks), chunk_size):
                    chunk = manifest_tasks[i : i + chunk_size]
                    chunk_urls = manifest_urls[i : i + chunk_size]

                    scraped_favicons_list = await asyncio.gather(*chunk, return_exceptions=True)

                    # Filter out exceptions from results with explicit cast
                    filtered_scraped_favicons_list: list[list[dict[str, Any]]] = []
                    for result in scraped_favicons_list:
                        if isinstance(result, Exception):
                            # Log the specific exception that occurred during manifest processing
                            logger.warning(f"Exception during manifest processing: {result}")
                            filtered_scraped_favicons_list.append([])
                        else:
                            filtered_scraped_favicons_list.append(
                                cast(list[dict[str, Any]], result)
                            )

                    for manifest_absolute_url, scraped_favicons_result in zip(
                        chunk_urls, filtered_scraped_favicons_list
                    ):
                        for scraped_favicon in scraped_favicons_result:
                            # Check if the favicon URL already contains a scheme
                            favicon_src = scraped_favicon.get("src", "")
                            if favicon_src.startswith(("http://", "https://")):
                                favicon_url = favicon_src
                            else:
                                favicon_url = urljoin(manifest_absolute_url, favicon_src)
                            favicons.append({"href": favicon_url})

            # Include the default "favicon.ico" if it exists in domain root
            default_favicon_url = await self.scraper.get_default_favicon(scraped_url)
            if default_favicon_url is not None:
                favicons.append({"href": default_favicon_url})

        except Exception as e:
            logger.info(f"Exception {e} while extracting favicons for {scraped_url}")
            pass

        return favicons

    async def _get_best_favicon(self, favicons: list[dict[str, Any]], min_width: int) -> str:
        """Asynchronous method to find the best favicon"""
        urls = [self._fix_url(favicon["href"]) for favicon in favicons]
        masked_svg_indices = [i for i, favicon in enumerate(favicons) if "mask" in favicon]

        best_favicon_url = ""
        best_favicon_width = 0

        # Process favicons in chunks to limit concurrent connections
        chunk_size = 20
        all_favicon_images = []

        for chunk_urls in itertools.batched(urls, chunk_size):
            chunk_images = await self.favicon_downloader.download_multiple_favicons(
                list(chunk_urls)
            )
            all_favicon_images.extend(chunk_images)

        favicon_images = all_favicon_images

        # First pass: Look for SVG favicons (they are priority)
        for i, (favicon, image) in enumerate(zip(favicons, favicon_images)):
            if image is None or "image/" not in image.content_type:
                continue

            # If favicon is an SVG and not masked, return it immediately
            if image.content_type == "image/svg+xml" and i not in masked_svg_indices:
                return urls[i]

        # Second pass: Look for the highest resolution bitmap favicon
        for i, (favicon, image) in enumerate(zip(favicons, favicon_images)):
            if image is None or "image/" not in image.content_type:
                continue

            try:
                width = self._get_favicon_smallest_dimension(image)
                if width > best_favicon_width:
                    best_favicon_url = urls[i]
                    best_favicon_width = width
            except Exception as e:
                logger.warning(f"Exception {e} for favicon {favicon}")

        logger.debug(f"Best favicon url: {best_favicon_url}, width: {best_favicon_width}")
        return best_favicon_url if best_favicon_width >= min_width else ""

    async def _get_favicon(self, scraped_url: str, min_width: int) -> str:
        """Extract all favicons for an already opened URL and return the one that satisfies the
        minimum width criteria. If multiple favicons satisfy the criteria then return the one
        with the highest resolution.
        """
        favicons: list[dict[str, Any]] = await self._extract_favicons(scraped_url)
        logger.info(
            f"{len(favicons)} favicons extracted for {scraped_url}. Favicons are: {favicons}"
        )
        return await self._get_best_favicon(favicons, min_width)

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

    def get_domain_metadata(
        self, domains_data: list[dict[str, Any]], favicon_min_width: int
    ) -> list[dict[str, Optional[str]]]:
        """Extract domain metadata for each domain, processing all concurrently"""
        return asyncio.run(self._process_domains_async(domains_data, favicon_min_width))

    async def _process_domains_async(
        self, domains_data: list[dict[str, Any]], favicon_min_width: int
    ) -> list[dict[str, Optional[str]]]:
        """Process domains in chunks to limit resource consumption."""
        chunk_size = 100
        filtered_results: list[dict[str, Optional[str]]] = []

        for i in range(0, len(domains_data), chunk_size):
            chunk = domains_data[i : i + chunk_size]
            tasks = [
                self._process_single_domain(domain_data, favicon_min_width)
                for domain_data in chunk
            ]
            logger.info(
                f"Processing chunk of {len(chunk)} domains concurrently "
                f"({i + 1}-{min(i + chunk_size, len(domains_data))} of {len(domains_data)})"
            )
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

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
        self, domain_data: dict[str, Any], favicon_min_width: int
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
                    favicon = await self._get_favicon(scraped_base_url, favicon_min_width)
                    second_level_domain = self._get_second_level_domain(domain, suffix)
                    title = self._get_title(second_level_domain)

            return {
                "url": scraped_base_url,
                "title": title,
                "icon": favicon,
                "domain": second_level_domain,
            }
        except Exception as e:
            logger.error(f"Error processing domain {domain_data.get('domain', 'unknown')}: {e}")
            # Return a default dict in case of error.
            return {"url": None, "title": None, "icon": None, "domain": None}
