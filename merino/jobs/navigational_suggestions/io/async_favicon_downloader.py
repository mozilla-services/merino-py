"""Async favicon downloader for fetching favicons from the web"""

import asyncio
import logging
from typing import Optional

import httpx

from merino.jobs.navigational_suggestions.constants import REQUEST_HEADERS, TIMEOUT
from merino.utils.gcs.models import Image
from merino.utils.http_client import create_http_client

logger = logging.getLogger(__name__)


class AsyncFaviconDownloader:
    """Download favicons asynchronously using async HTTP client."""

    def __init__(self) -> None:
        self.session = create_http_client(
            request_timeout=float(TIMEOUT),
            connect_timeout=float(TIMEOUT),
        )

    async def requests_get(self, url: str) -> Optional[httpx.Response]:
        """Fetch URL and return response if status is 200."""
        try:
            response = await self.session.get(url, headers=REQUEST_HEADERS, follow_redirects=True)
            return response if response.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to fetch URL {url}: {e}")
            return None

    async def download_favicon(self, url: str) -> Optional[Image]:
        """Download favicon and return Image object with content and metadata."""
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
        except Exception as e:
            logger.debug(f"Failed to download favicon from {url}: {e}")
            return None

    async def download_multiple_favicons(self, urls: list[str]) -> list[Optional[Image]]:
        """Download multiple favicons concurrently using asyncio.gather."""
        tasks = [self.download_favicon(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [None if isinstance(r, BaseException) else r for r in results]

    async def close(self) -> None:
        """Close HTTP session and release resources."""
        if hasattr(self, "session"):
            await self.session.aclose()

    async def reset(self) -> None:
        """Close current session and create a new one."""
        try:
            await self.close()
            self.session = create_http_client(
                request_timeout=float(TIMEOUT),
                connect_timeout=float(TIMEOUT),
            )
        except Exception as ex:
            logger.warning(f"Error occurred when resetting favicon downloader: {ex}")
