"""Web scraper for extracting data from websites"""

import logging
from typing import Optional, cast

import requests
from bs4 import BeautifulSoup
from mechanicalsoup import StatefulBrowser

from merino.jobs.navigational_suggestions.constants import (
    ALLOW_REDIRECTS,
    PARSER,
)
from merino.jobs.navigational_suggestions.constants import REQUEST_HEADERS, TIMEOUT

logger = logging.getLogger(__name__)


class WebScraper:
    """Website scraper using MechanicalSoup. Use as context manager."""

    def __init__(self) -> None:
        session: requests.Session = requests.Session()
        self.browser = StatefulBrowser(
            session=session,
            soup_config={"features": PARSER},
            raise_on_404=False,
            user_agent=REQUEST_HEADERS["User-Agent"],
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def open(self, url: str) -> Optional[str]:
        """Open URL and return final URL after redirects, or None if failed."""
        try:
            self.browser.open(url, timeout=TIMEOUT, allow_redirects=ALLOW_REDIRECTS)
            return str(self.browser.url)
        except Exception as e:
            logger.debug(f"Failed to open URL {url}: {e}")
            return None

    def scrape_title(self) -> Optional[str]:
        """Extract title from page header."""
        try:
            title_element = self.browser.page.find("head").find("title")
            if title_element:
                return str(title_element.get_text())
            return None
        except Exception as e:
            logger.debug(f"Exception while scraping title: {e}")
            return None

    def get_page(self) -> Optional[BeautifulSoup]:
        """Get the current page's BeautifulSoup object."""
        return cast(Optional[BeautifulSoup], self.browser.page)

    def get_current_url(self) -> Optional[str]:
        """Get current URL after any redirects."""
        try:
            return str(self.browser.url) if self.browser.url else None
        except Exception:
            return None

    def close(self) -> None:
        """Close browser session and clean up resources."""
        try:
            if hasattr(self.browser, "session") and self.browser.session:
                self.browser.session.close()

            if hasattr(self.browser, "_browser"):
                self.browser._browser = None

            self.browser.close()
        except Exception as ex:
            logger.warning(f"Error occurred when closing scraper session: {ex}")
