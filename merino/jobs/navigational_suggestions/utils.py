"""Utilities for navigational suggestions job"""

import requests
from pydantic import BaseModel

FIREFOX_UA: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.3; rv:111.0) Gecko/20100101 "
    "Firefox/111.0"
)

TIMEOUT: int = 10


class FaviconImage(BaseModel):
    """Data model for favicon image contents and associated metadata."""

    content: bytes
    content_type: str


class FaviconDownloader:
    """Download favicon from the web"""

    def download_favicon(self, url: str) -> FaviconImage:
        """Download the favicon from the given url.

        Args:
            url: favicon URL
        Returns:
            FaviconImage: favicon image content and associated metadata
        """
        response = requests.get(
            url,
            headers={"User-agent": FIREFOX_UA},
            timeout=TIMEOUT,
        )
        return FaviconImage(
            content=response.content,
            content_type=str(response.headers.get("Content-Type")),
        )
