"""Domain processor for orchestrating domain metadata extraction"""

import asyncio
import contextvars
import logging
from typing import Any, Optional, TYPE_CHECKING

import tldextract

from merino.jobs.navigational_suggestions.enrichments.custom_favicons import get_custom_favicon_url
from merino.jobs.navigational_suggestions.favicon.favicon_extractor import FaviconExtractor
from merino.jobs.navigational_suggestions.favicon.favicon_processor import FaviconProcessor
from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import FaviconScraper
from merino.jobs.navigational_suggestions.scrapers.web_scraper import WebScraper
from merino.jobs.navigational_suggestions.utils import get_base_url
from merino.jobs.navigational_suggestions.io import AsyncFaviconDownloader
from merino.jobs.navigational_suggestions.validators import (
    get_second_level_domain,
    get_title_or_fallback,
    is_domain_blocked,
    sanitize_title,
)
from merino.jobs.utils.system_monitor import SystemMonitor

if TYPE_CHECKING:
    from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import (
        DomainMetadataUploader,
    )

logger = logging.getLogger(__name__)

# Context variable for the current web scraper
current_web_scraper: contextvars.ContextVar[WebScraper] = contextvars.ContextVar(
    "current_web_scraper"
)


class DomainProcessor:
    """Process domains to extract metadata and favicons. Checks custom favicons first,
    falls back to web scraping. Processes in chunks for memory management.
    """

    def __init__(
        self,
        blocked_domains: set[str],
        favicon_downloader: Optional[AsyncFaviconDownloader] = None,
        chunk_size: int = 25,
    ) -> None:
        self.blocked_domains = blocked_domains
        self.favicon_downloader = favicon_downloader or AsyncFaviconDownloader()
        self.chunk_size = chunk_size

    def process_domain_metadata(
        self,
        domains_data: list[dict[str, Any]],
        favicon_min_width: int,
        uploader: "DomainMetadataUploader",
        enable_monitoring: bool = False,
    ) -> list[dict[str, Optional[str]]]:
        """Extract domain metadata, process concurrently in chunks, upload favicons to GCS."""
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
        uploader: "DomainMetadataUploader",
        enable_monitoring: bool = False,
    ) -> list[dict[str, Optional[str]]]:
        """Process domains in chunks to limit resource consumption."""
        filtered_results: list[dict[str, Optional[str]]] = []
        total_chunks = (len(domains_data) + self.chunk_size - 1) // self.chunk_size

        # Initialize monitor only if monitoring is enabled
        monitor = None
        if enable_monitoring:
            monitor = SystemMonitor()
            logger.info("Starting domain processing with system monitoring enabled")
            monitor.log_metrics(chunk_num=0, total_chunks=total_chunks)
        else:
            logger.info("Starting domain processing (monitoring disabled)")

        for i in range(0, len(domains_data), self.chunk_size):
            end_idx = min(i + self.chunk_size, len(domains_data))
            chunk = domains_data[i:end_idx]
            chunk_num = i // self.chunk_size + 1

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
        self,
        domain_data: dict[str, Any],
        favicon_min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> dict[str, Optional[str]]:
        """Process single domain: check if blocked, try custom favicon, fall back to scraping."""
        domain: str = domain_data["domain"]
        suffix: str = domain_data["suffix"]

        # Check if domain is in our internal blocklist
        if is_domain_blocked(domain, suffix, self.blocked_domains):
            return {
                "url": None,
                "title": None,
                "icon": None,
                "domain": None,
                "error_reason": "domain_in_blocklist",
            }

        # Extract second level domain for processing
        e = tldextract.extract(domain)
        second_level_domain: str = get_second_level_domain(domain, suffix)

        # STEP 1: Check custom favicons FIRST (primary source)
        custom_result = await self._try_custom_favicon(
            e.domain, domain, second_level_domain, uploader
        )
        if custom_result:
            custom_result["error_reason"] = None
            return custom_result

        # STEP 2: Fall back to normal scraping process
        scraping_result = await self._try_scraping(
            domain, second_level_domain, favicon_min_width, uploader
        )
        return scraping_result

    async def _try_custom_favicon(
        self,
        domain_key: str,
        full_domain: str,
        second_level_domain: str,
        uploader: "DomainMetadataUploader",
    ) -> Optional[dict[str, Optional[str]]]:
        """Try custom favicon lookup and upload."""
        custom_favicon_url = get_custom_favicon_url(domain_key)
        if not custom_favicon_url:
            return None

        try:
            # If URL is already from our CDN, use it directly
            if custom_favicon_url.startswith(f"https://{uploader.uploader.cdn_hostname}"):
                favicon = custom_favicon_url
            else:
                # Download and upload the custom favicon
                favicon_image = await self.favicon_downloader.download_favicon(custom_favicon_url)
                if favicon_image:
                    dst_favicon_name = uploader.destination_favicon_name(favicon_image)
                    favicon = uploader.upload_image(
                        favicon_image, dst_favicon_name, forced_upload=uploader.force_upload
                    )
                else:
                    favicon = ""

            if favicon:
                title = second_level_domain.capitalize()
                scraped_base_url = f"https://{full_domain}"
                logger.info(f"Used custom favicon for: {full_domain}")

                return {
                    "url": scraped_base_url,
                    "title": title,
                    "icon": favicon,
                    "domain": second_level_domain,
                }

        except Exception as e:
            logger.warning(f"Failed to process custom favicon for {full_domain}: {e}")

        return None

    async def _try_scraping(
        self,
        domain: str,
        second_level_domain: str,
        favicon_min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> dict[str, Optional[str]]:
        """Scrape domain website for metadata and favicon."""
        error_reason = None
        with WebScraper() as web_scraper:
            # Set the context variable for this task's context
            token = current_web_scraper.set(web_scraper)

            try:
                # Try to open the domain
                url: str = f"https://{domain}"
                full_url: Optional[str] = web_scraper.open(url)

                if full_url is None:
                    # Retry with www. prefix as some domains require it
                    url = f"https://www.{domain}"
                    full_url = web_scraper.open(url)

                # Check if we successfully opened a page on the correct domain
                if full_url and domain in full_url:
                    # Check for bot blocking before processing
                    if web_scraper.is_bot_blocked():
                        status_code = web_scraper.get_status_code()
                        error_reason = f"blocked_by_bot_protection: HTTP {status_code or 'N/A'}"
                        logger.debug(f"Bot protection detected for domain: {domain}")
                    else:
                        scraped_base_url = get_base_url(full_url)

                        # Extract favicon
                        favicon, favicon_error = await self._extract_and_process_favicon(
                            web_scraper, scraped_base_url, favicon_min_width, uploader
                        )

                        # Extract title
                        title = self._extract_title(web_scraper, second_level_domain)

                        if favicon:
                            logger.info(f"Found favicon for domain: {domain}")

                        return {
                            "url": scraped_base_url,
                            "title": title,
                            "icon": favicon,
                            "domain": second_level_domain,
                            "error_reason": favicon_error if not favicon else None,
                        }
                else:
                    # Capture more granular error
                    if full_url:
                        error_reason = (
                            f"domain_mismatch_after_redirect: expected {domain}, got {full_url}"
                        )
                    else:
                        # Check HTTP status code if available
                        status_code = web_scraper.get_status_code()
                        if status_code:
                            if status_code == 403:
                                error_reason = "http_403_forbidden: access denied by server"
                            elif status_code == 503:
                                error_reason = (
                                    "http_503_service_unavailable: server temporarily unavailable"
                                )
                            elif status_code >= 500:
                                error_reason = f"http_{status_code}_server_error: server error"
                            elif status_code >= 400:
                                error_reason = f"http_{status_code}_client_error: client error"
                            else:
                                error_reason = f"http_{status_code}: unexpected status code"
                        else:
                            error_reason = "connection_failed: timeout or network error"

            except Exception as e:
                logger.debug(f"Exception processing domain {domain}: {e}")
                # Capture specific exception types for better debugging
                exception_type = e.__class__.__name__
                error_reason = f"scraping_exception_{exception_type}: {str(e)}"
            finally:
                # Reset the context variable
                current_web_scraper.reset(token)

        # Return empty result if scraping failed
        return {
            "url": None,
            "title": None,
            "icon": None,
            "domain": None,
            "error_reason": error_reason,
        }

    async def _extract_and_process_favicon(
        self,
        web_scraper: WebScraper,
        scraped_url: str,
        min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> tuple[str, Optional[str]]:
        """Extract favicons from page and upload the best one.

        Returns:
            Tuple of (favicon_url, error_reason) where error_reason is None if successful
        """
        try:
            # Create components for favicon extraction
            favicon_scraper = FaviconScraper(self.favicon_downloader)
            favicon_extractor = FaviconExtractor(favicon_scraper)
            favicon_processor = FaviconProcessor(self.favicon_downloader, scraped_url)

            # Extract favicons from the page
            page = web_scraper.get_page()
            favicons = await favicon_extractor.extract_favicons(page, scraped_url, max_icons=5)

            if not favicons:
                return "", "no_favicons_found"

            # Process and upload the best favicon
            favicon_url, error = await favicon_processor.process_and_upload_best_favicon(
                favicons, min_width, uploader
            )

            return favicon_url, error

        except Exception as e:
            logger.error(f"Error extracting and processing favicon: {e}")
            return "", f"favicon_extraction_exception: {str(e)}"

    def _extract_title(self, web_scraper: WebScraper, fallback: str) -> str:
        """Extract and validate page title, or return capitalized fallback."""
        try:
            raw_title = web_scraper.scrape_title()
            sanitized_title = sanitize_title(raw_title)
            return get_title_or_fallback(sanitized_title, fallback)
        except Exception as e:
            logger.debug(f"Error extracting title: {e}")
            return fallback.capitalize()
