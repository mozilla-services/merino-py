"""Extract domain metadata from domain data"""

import asyncio
import logging
import contextvars
import tldextract

from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel
from mechanicalsoup import StatefulBrowser

from merino.jobs.navigational_suggestions.domain_metadata_uploader import DomainMetadataUploader
from merino.jobs.utils.system_monitor import SystemMonitor
from merino.jobs.navigational_suggestions.utils import (
    REQUEST_HEADERS,
    TIMEOUT,
    AsyncFaviconDownloader,
)
from merino.jobs.navigational_suggestions.custom_favicons import get_custom_favicon_url

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
    ALLOW_REDIRECTS = True

    browser: StatefulBrowser
    request_client: AsyncFaviconDownloader
    parser: str = "html.parser"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __init__(self) -> None:
        session: requests.Session = requests.Session()
        self.browser = StatefulBrowser(
            session=session,
            soup_config={"features": self.parser},
            raise_on_404=False,
            user_agent=REQUEST_HEADERS["User-Agent"],
        )
        self.request_client = AsyncFaviconDownloader()

    def open(self, url: str) -> Optional[str]:
        """Open the given url for scraping.

        Args:
            url: URL to open
        Returns:
            Optional[str]: Full URL that was opened
        """
        try:
            self.browser.open(url, timeout=TIMEOUT, allow_redirects=self.ALLOW_REDIRECTS)
            return str(self.browser.url)
        except Exception:
            return None

    def scrape_favicon_data(self) -> FaviconData:
        """Scrape the favicon data for an already opened URL.

        Returns:
            FaviconData: Favicon data for a URL
        """
        return FaviconData(
            links=[link.attrs for link in self.browser.page.select(self.LINK_SELECTOR)],
            metas=[meta.attrs for meta in self.browser.page.select(self.META_SELECTOR)],
            manifests=[
                manifest.attrs
                for manifest in self.browser.page.select(f"head {self.MANIFEST_SELECTOR}")
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
        default_favicon_url: str = urljoin(url, "favicon.ico")
        try:
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
            return str(self.browser.page.find("head").find("title").get_text())
        except Exception as e:
            logger.info(f"Exception: {e} while scraping title")
            return None

    def close(self) -> None:
        """Close the scraper browser session properly"""
        try:
            if hasattr(self.browser, "session") and self.browser.session:
                self.browser.session.close()

            if hasattr(self.browser, "_browser"):
                self.browser._browser = None

            self.browser.close()
        except Exception as ex:
            logger.warning(f"Error occurred when closing scraper session: {ex}")


# Create a context variable for the current scraper
current_scraper: contextvars.ContextVar[Scraper] = contextvars.ContextVar("current_scraper")


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
        "Unsupported browser",
    ]

    # Constants for favicon URL validation
    MANIFEST_JSON_BASE64_MARKER = "/application/manifest+json;base64,"

    # List of blocked (second level) domains
    blocked_domains: set[str]
    favicon_downloader: AsyncFaviconDownloader

    def __init__(
        self,
        blocked_domains: set[str],
        favicon_downloader: AsyncFaviconDownloader = AsyncFaviconDownloader(),
    ) -> None:
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

    async def _extract_favicons(
        self,
        scraped_url: str,
        max_icons: int = 5,
    ) -> list[dict[str, Any]]:
        """Extract a limited number of favicons for an already opened url"""
        self._current_base_url = scraped_url
        favicons: list[dict[str, Any]] = []

        scraper = current_scraper.get()

        try:
            # Get the most common favicon sources first
            favicon_data: FaviconData = scraper.scrape_favicon_data()

            # First priority: process standard link icons (usually higher quality)
            for favicon in favicon_data.links[:max_icons]:
                favicon_url = favicon["href"]
                if self._is_problematic_favicon_url(favicon_url):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith("//"):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                favicon["_source"] = "link"
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
                favicon["_source"] = "meta"
                favicons.append(favicon)

                # Check if we've reached our limit
                if len(favicons) >= max_icons:
                    return favicons

            # If still below max, try the default favicon
            if len(favicons) < max_icons:
                default_favicon_url = await scraper.get_default_favicon(scraped_url)
                if default_favicon_url is not None:
                    favicons.append({"href": default_favicon_url, "_source": "default"})

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
                    manifest_icons = await scraper.scrape_favicons_from_manifest(
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

                        favicons.append({"href": favicon_url, "_source": "manifest"})

                        # Check if we've reached our limit
                        if len(favicons) >= max_icons:
                            break

                except Exception as e:
                    logger.warning(f"Error processing manifest: {e}")

        except Exception as e:
            logger.error(f"Exception extracting favicons: {e}")

        return favicons

    def _is_better_favicon(
        self, favicon: dict[str, Any], width: int, best_width: int, best_source: str
    ) -> bool:
        """Check if this favicon is better than the current best using Firefox prioritization"""
        source = favicon.get("_source", "default")
        source_priority = {"link": 1, "meta": 2, "manifest": 3, "default": 4}

        current_priority = source_priority.get(source, 4)
        best_priority = source_priority.get(best_source, 4)

        if current_priority < best_priority:
            return True

        if current_priority == best_priority and width > best_width:
            return True

        return False

    async def _process_favicon(
        self,
        scraped_url: str,
        min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> str:
        """Extract all favicons for an already opened URL and return the one that satisfies the
        minimum width criteria. If multiple favicons satisfy the criteria then upload the one
        with the highest resolution and return the url.
        """
        # Extract favicon candidates (with a reasonable limit)
        favicons = await self._extract_favicons(scraped_url, max_icons=5)

        return await self._upload_best_favicon(favicons, min_width, uploader)

    async def _upload_best_favicon(
        self, favicons: list[dict[str, Any]], min_width: int, uploader: DomainMetadataUploader
    ) -> str:
        """Asynchronous method to find the best favicon with improved memory management"""
        try:
            # Get URLs and filter out empty or problematic ones
            urls = [self._fix_url(favicon.get("href", "")) for favicon in favicons]
            urls = [url for url in urls if url and "://" in url]

            # If we have no valid URLs after filtering, return empty string
            if not urls:
                return ""

            # Identify masked SVG indices upfront
            masked_svg_indices = [i for i, favicon in enumerate(favicons) if "mask" in favicon]

            # Tracking variables for best favicon
            best_favicon_url = ""
            best_favicon_width = 0
            best_favicon_source = "default"

            # Prioritization: Process SVGs first, then bitmap images
            # This allows us to exit early once we find a good SVG
            svg_urls = []
            svg_indices = []
            bitmap_urls = []
            bitmap_indices = []

            # Categorize URLs by likely type
            for i, url in enumerate(urls):
                if url.lower().endswith(".svg"):
                    svg_urls.append(url)
                    svg_indices.append(i)
                else:
                    bitmap_urls.append(url)
                    bitmap_indices.append(i)

            # Process SVGs first (since we prioritize them)
            if svg_urls:
                try:
                    svg_images = await self.favicon_downloader.download_multiple_favicons(svg_urls)

                    # Process SVG images with proper cleanup
                    for local_idx, (image, url) in enumerate(zip(svg_images, svg_urls)):
                        original_idx = svg_indices[local_idx]

                        try:
                            if image is None or "image/svg+xml" not in image.content_type:
                                continue

                            # If it's not a masked SVG, we can select it immediately
                            if original_idx not in masked_svg_indices:
                                # Process and upload the SVG
                                dst_favicon_name = uploader.destination_favicon_name(image)
                                try:
                                    result = uploader.upload_image(
                                        image, dst_favicon_name, forced_upload=True
                                    )
                                    # Return early - SVGs are our top priority
                                    return str(result)
                                except Exception as e:
                                    logger.warning(f"Failed to upload SVG favicon: {e}")
                                    # Fall back to original URL for SVG if upload fails
                                    return url
                        except Exception as e:
                            logger.warning(f"Exception for favicon at position {local_idx}: {e}")
                        finally:
                            # Ensure we clean up each image individually
                            if image:
                                del image

                    # Clear SVG processing variables
                    del svg_images
                except Exception as e:
                    logger.error(f"Error during SVG favicon processing: {e}")

            # If we reach here, no good SVG was found - process bitmap images
            if bitmap_urls:
                try:
                    # Process bitmap favicons in smaller batches to manage memory better
                    BATCH_SIZE = 5
                    for i in range(0, len(bitmap_urls), BATCH_SIZE):
                        batch_urls = bitmap_urls[i : i + BATCH_SIZE]
                        batch_indices = bitmap_indices[i : i + BATCH_SIZE]

                        try:
                            # Download this batch
                            batch_images = (
                                await self.favicon_downloader.download_multiple_favicons(
                                    batch_urls
                                )
                            )

                            # Process images in this batch
                            for local_idx, (image, url) in enumerate(
                                zip(batch_images, batch_urls)
                            ):
                                original_idx = batch_indices[local_idx]

                                try:
                                    if image is None or "image/" not in image.content_type:
                                        continue

                                    # Get image dimensions
                                    try:
                                        width, height = image.get_dimensions()
                                        width_val = min(width, height)
                                    except Exception as e:
                                        logger.warning(
                                            f"Exception for favicon at position {local_idx}: {e}"
                                        )
                                        continue

                                    # Check if this is a better favicon than what we've seen so far
                                    if self._is_better_favicon(
                                        favicons[original_idx],
                                        width_val,
                                        best_favicon_width,
                                        best_favicon_source,
                                    ):
                                        try:
                                            dst_favicon_name = uploader.destination_favicon_name(
                                                image
                                            )
                                            favicon_url = uploader.upload_image(
                                                image, dst_favicon_name, forced_upload=True
                                            )
                                            best_favicon_url = favicon_url
                                            best_favicon_width = width_val
                                            best_favicon_source = favicons[original_idx].get(
                                                "_source", "default"
                                            )
                                        except Exception as e:
                                            logger.warning(f"Failed to upload bitmap favicon: {e}")
                                            # Fallback to original URL if upload fails
                                            if self._is_better_favicon(
                                                favicons[original_idx],
                                                width_val,
                                                best_favicon_width,
                                                best_favicon_source,
                                            ):
                                                best_favicon_url = url
                                                best_favicon_width = width_val
                                                best_favicon_source = favicons[original_idx].get(
                                                    "_source", "default"
                                                )
                                except Exception as e:
                                    logger.warning(
                                        f"Exception for favicon at position {local_idx}: {e}"
                                    )
                                finally:
                                    # Ensure we clean up each image individually
                                    if image:
                                        del image

                            # Clear batch variables
                            del batch_images
                        except Exception as e:
                            logger.error(f"Error processing bitmap batch: {e}")

                except Exception as e:
                    logger.error(f"Error during bitmap favicon processing: {e}")

                # Return the best favicon URL if it meets the minimum width requirement
                return best_favicon_url if best_favicon_width >= min_width else ""
            return ""
        except Exception as e:
            logger.error(f"Unexpected error in _upload_best_favicon: {e}")
            return ""

    def _extract_title(self) -> Optional[str]:
        """Extract title for a url"""
        # Get the scraper from the context
        scraper = current_scraper.get()

        title: Optional[str] = scraper.scrape_title()
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
        enable_monitoring: bool = False,
    ) -> list[dict[str, Optional[str]]]:
        """Extract domain metadata for each domain, processing all concurrently and upload the
        favicons directly to the Google Cloud bucket
        """
        logger.info(f"Starting to process {len(domains_data)} domains")
        results = asyncio.run(
            self._process_domains(domains_data, favicon_min_width, uploader, enable_monitoring)
        )
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
        enable_monitoring: bool = False,
    ) -> list[dict[str, Optional[str]]]:
        """Process domains in chunks to limit resource consumption."""
        # Reduce batch size to decrease memory consumption and network load
        chunk_size = 25
        filtered_results: list[dict[str, Optional[str]]] = []
        total_chunks = (len(domains_data) + chunk_size - 1) // chunk_size

        # Initialize monitor only if monitoring is enabled
        monitor = None
        if enable_monitoring:
            monitor = SystemMonitor()
            logger.info("Starting domain processing with system monitoring enabled")
            monitor.log_metrics(chunk_num=0, total_chunks=total_chunks)
        else:
            logger.info("Starting domain processing (monitoring disabled)")

        for i in range(0, len(domains_data), chunk_size):
            end_idx = min(i + chunk_size, len(domains_data))
            chunk = domains_data[i:end_idx]
            chunk_num = i // chunk_size + 1

            logger.info(
                f"Processing chunk {chunk_num}/{total_chunks} ({i + 1}-{end_idx} of {len(domains_data)})"
            )

            tasks = [
                self._process_single_domain(domain_data, favicon_min_width, uploader)
                for domain_data in chunk
            ]

            # Process current chunk with gather
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Error processing domain: {result}")
                else:
                    if not isinstance(result, dict):
                        logger.error(f"Unexpected result type: {result}")
                        continue
                    filtered_results.append(result)

            # Reset the FaviconDownloader instead of recreating
            await self.favicon_downloader.reset()

            # Log system metrics after processing this chunk if monitoring is enabled
            if monitor:
                monitor.log_metrics(chunk_num=chunk_num, total_chunks=total_chunks)

        logger.info("Domain processing complete")
        if monitor:
            monitor.log_metrics()

        return filtered_results

    async def _process_single_domain(
        self, domain_data: dict[str, Any], favicon_min_width: int, uploader: DomainMetadataUploader
    ) -> dict[str, Optional[str]]:
        """Process a single domain asynchronously and always return a valid dict."""
        scraped_base_url: Optional[str] = None
        favicon: str = ""
        title: str = ""
        second_level_domain: str = ""

        domain: str = domain_data["domain"]
        suffix: str = domain_data["suffix"]

        e = tldextract.extract(domain)

        # STEP 1: Check custom favicons FIRST (primary source)
        custom_favicon_url = get_custom_favicon_url(e.domain)
        if custom_favicon_url:
            try:
                # If URL is already from our CDN, use it directly
                if custom_favicon_url.startswith(f"https://{uploader.uploader.cdn_hostname}"):
                    favicon = custom_favicon_url
                else:
                    # Download the favicon asynchronously (we're already in async context)
                    favicon_image = await self.favicon_downloader.download_favicon(
                        custom_favicon_url
                    )
                    if favicon_image:
                        # Upload the image synchronously
                        dst_favicon_name = uploader.destination_favicon_name(favicon_image)
                        favicon = uploader.upload_image(
                            favicon_image, dst_favicon_name, forced_upload=uploader.force_upload
                        )
                    else:
                        favicon = ""

                if favicon:
                    second_level_domain = self._get_second_level_domain(domain, suffix)
                    title = second_level_domain.capitalize()
                    scraped_base_url = f"https://{domain}"
                    logger.info(f"Used custom favicon for: {domain}")

                    return {
                        "url": scraped_base_url,
                        "title": title,
                        "icon": favicon,
                        "domain": second_level_domain,
                    }
            except Exception as e:
                logger.warning(f"Failed to upload custom favicon for {domain}: {e}")
                # Continue to scraping fallback below

        # STEP 2: Fall back to normal scraping process only if no custom favicon
        with Scraper() as domain_scraper:
            # Set the context variable for this task's context
            token = current_scraper.set(domain_scraper)
            try:
                if not self._is_domain_blocked(domain, suffix):
                    url: str = f"https://{domain}"
                    full_url: Optional[str] = domain_scraper.open(url)

                    if full_url is None:
                        # Retry with www. in the url as some domains require it explicitly
                        url = f"https://www.{domain}"
                        full_url = domain_scraper.open(url)

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
            finally:
                # Reset the context variable
                current_scraper.reset(token)
