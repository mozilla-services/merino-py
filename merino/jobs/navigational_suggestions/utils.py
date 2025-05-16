"""Utilities for navigational suggestions job"""

import asyncio
import logging
import httpx

from typing import Optional, List
from pprint import pprint

from merino.utils.gcs.models import Image
from merino.utils.http_client import create_http_client

REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/114.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
}

TIMEOUT: int = 15

logger = logging.getLogger(__name__)


class AsyncFaviconDownloader:
    """Download favicon from the web asynchronously"""

    def __init__(self) -> None:
        self.session = create_http_client(
            request_timeout=float(TIMEOUT),
            connect_timeout=float(TIMEOUT),
        )

    async def requests_get(self, url: str) -> Optional[httpx.Response]:
        """Open a given url and return the response asynchronously.

        Args:
            url: URL to open
        Returns:
            Optional[httpx.Response]: Response object
        """
        try:
            response = await self.session.get(url, headers=REQUEST_HEADERS, follow_redirects=True)
            return response if response.status_code == 200 else None
        except Exception:
            return None

    async def download_favicon(self, url: str) -> Optional[Image]:
        """Download the favicon from the given url asynchronously.

        Args:
            url: favicon URL
        Returns:
            Image: favicon image content and associated metadata
        """
        try:
            response = await self.session.get(url, headers=REQUEST_HEADERS, follow_redirects=True)
            if response.status_code == 200:
                content = response.content
                content_type = response.headers.get("Content-Type", "image/unknown")
                return Image(
                    content=content,
                    content_type=str(content_type),
                )
            return None
        except Exception:
            return None

    async def download_multiple_favicons(self, urls: List[str]) -> List[Optional[Image]]:
        """Download multiple favicons concurrently.

        Args:
            urls: List of favicon URLs
        Returns:
            List of favicon images
        """
        # Create tasks without semaphore control
        tasks = [self.download_favicon(url) for url in urls]

        # Handle the exceptions internally to maintain return type consistency
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [None if isinstance(r, BaseException) else r for r in results]

    async def close(self) -> None:
        """Close the aiohttp session."""
        if hasattr(self, "session"):
            await self.session.aclose()

    async def reset(self) -> None:
        """Reset the downloader by closing the current session and creating a new one."""
        try:
            # Close the current session
            await self.close()

            # Create a new session
            self.session = create_http_client(
                request_timeout=float(TIMEOUT),
                connect_timeout=float(TIMEOUT),
            )
        except Exception as ex:
            logger.warning(f"Error occurred when resetting favicon downloader: {ex}")


class DomainMetadataExtractionErrorsCollector:
    """Collects metadata extraction errors for multiple domains."""

    # Maps domain names to a list of failure reasons.
    domain_failure_reasons: dict[str, list[str]]

    def __init__(self) -> None:
        # Initialize the failure reasons dictionary.
        self.domain_failure_reasons = {}

    def add_failure_reason_for_domain(self, *, domain: str, failure_reason: str):
        """Add a failure reason for a specific domain."""
        if domain not in self.domain_failure_reasons:
            self.domain_failure_reasons[domain] = []

        self.domain_failure_reasons[domain].append(failure_reason)

    def print_failures(self) -> None:
        """Pretty print the collected domain failure reasons."""
        logger.warning(f"@@@@@@@@@@@@@@@@@@@ \n{self.domain_failure_reasons}")
