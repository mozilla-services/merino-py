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

# HTML elements commonly used by bot protection services (Cloudflare, etc.)
# Structure: list of (attribute_name, attribute_value) tuples for div elements
# Future: expand this list as new bot-blocking patterns are discovered
BOT_BLOCKING_ELEMENTS = [
    ("id", "challenge-form"),  # Cloudflare challenge
    ("class_", "cf-browser-verification"),  # Cloudflare verification
]


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
            response = self.browser.open(url, timeout=TIMEOUT, allow_redirects=ALLOW_REDIRECTS)
            if response and response.status_code >= 400:
                logger.debug(f"HTTP {response.status_code} error for URL {url}")
            return str(self.browser.url)
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout opening URL {url}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"Connection error opening URL {url}: {e}")
            return None
        except requests.exceptions.TooManyRedirects:
            logger.debug(f"Too many redirects for URL {url}")
            return None
        except requests.exceptions.SSLError as e:
            logger.debug(f"SSL error opening URL {url}: {e}")
            return None
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

    def get_status_code(self) -> Optional[int]:
        """Get HTTP status code of the last response."""
        try:
            if hasattr(self.browser, "response") and self.browser.response:
                return int(self.browser.response.status_code)
            return None
        except Exception:
            return None

    def is_bot_blocked(self) -> bool:
        """Check if page appears to be a bot-blocking or challenge page."""
        try:
            page = self.get_page()
            if not page:
                return False

            title = self.scrape_title()
            if title:
                title_lower = title.lower()
                # Check page title for common phrases used by bot-blocking services
                # (e.g., Cloudflare, Akamai, captcha pages, access denied pages)
                bot_indicators = [
                    "access denied",
                    "captcha",
                    "cloudflare",
                    "security check",
                    "robot or human",
                    "just a moment",
                    "checking your browser",
                    "ddos protection",
                    "are you a robot",
                    "bot protection",
                    "please verify",
                    "attention required",
                ]
                if any(indicator in title_lower for indicator in bot_indicators):
                    return True

            # Check for specific HTML elements commonly used by bot protection services
            # These elements are typically present on challenge/verification pages
            for attr, value in BOT_BLOCKING_ELEMENTS:
                if page.find("div", attrs={attr: value}):
                    return True

            return False
        except Exception:
            return False

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
