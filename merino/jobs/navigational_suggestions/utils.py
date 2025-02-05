"""Utilities for navigational suggestions job"""

import logging

import requests

from merino.utils.gcs.models import Image

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

TIMEOUT: int = 10

logger = logging.getLogger(__name__)


class FaviconDownloader:
    """Download favicon from the web"""

    def download_favicon(self, url: str) -> Image | None:
        """Download the favicon from the given url.

        Args:
            url: favicon URL
        Returns:
            Image: favicon image content and associated metadata
        """
        try:
            response = requests_get(url)
            return (
                Image(
                    content=response.content,
                    content_type=str(response.headers.get("Content-Type")),
                )
                if response
                else None
            )
        except Exception as e:
            logger.info(f"Exception {e} while downloading favicon {url}")
            return None


def requests_get(url: str) -> requests.Response | None:
    """Open a given url and return the response.

    Args:
        url: URL to open
    Returns:
        requests.Response | None: Response object
    """
    response: requests.Response = requests.get(
        url,
        headers=REQUEST_HEADERS,
        timeout=TIMEOUT,
    )
    return response if response.status_code == 200 else None
