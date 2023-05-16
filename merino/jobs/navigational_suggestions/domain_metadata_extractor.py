"""Extract domain metadata from domain data"""
import logging
from io import BytesIO
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image
from pydantic import BaseModel
from robobrowser import RoboBrowser

from merino.jobs.navigational_suggestions.utils import (
    FIREFOX_UA,
    TIMEOUT,
    FaviconDownloader,
    FaviconImage,
)

logger = logging.getLogger(__name__)


class FaviconData(BaseModel):
    """Data model for favicon information extracted from a website."""

    links: list[dict[str, Any]]
    metas: list[dict[str, Any]]
    url: str


class Scraper:
    """Website data extractor."""

    LINK_SELECTOR: str = (
        "link[rel=apple-touch-icon], link[rel=apple-touch-icon-precomposed],"
        'link[rel="icon shortcut"], link[rel="shortcut icon"], link[rel="icon"],'
        'link[rel="SHORTCUT ICON"], link[rel="fluid-icon"]'
    )
    META_SELECTOR: str = "meta[name=apple-touch-icon]"

    browser: RoboBrowser

    def __init__(self) -> None:
        self.browser = RoboBrowser(
            user_agent=FIREFOX_UA, parser="html.parser", allow_redirects=True
        )

    def scrape_favicon_data(self, url: str) -> FaviconData:
        """Scrape the favicon data from the given url.

        Args:
            url: URL to open and scrape
        Returns:
            str: Favicon data from the given URL
        """
        self.browser.open(url, timeout=TIMEOUT)
        return FaviconData(
            links=[link.attrs for link in self.browser.select(self.LINK_SELECTOR)],
            metas=[meta.attrs for meta in self.browser.select(self.META_SELECTOR)],
            url=self.browser.url,
        )

    def get_default_favicon(self, url: str) -> Optional[str]:
        """Return the default favicon for the given url.

        Args:
            url: URL to scrape for favicon at default location
        Returns:
            Optional[str]: Default favicon url if it exists
        """
        default_favicon_url = urljoin(url, "favicon.ico")
        response = requests.get(
            default_favicon_url,
            headers={"User-agent": FIREFOX_UA},
            timeout=TIMEOUT,
        )
        return default_favicon_url if response.status_code == 200 else None

    def scrape_url_and_title(self, url: str) -> tuple[str, str]:
        """Scrape the title from the header of the given url and return it along with the
        final redirected url.

        Args:
            url: URL to open and scrape
        Returns:
            tuple[str,str]: The final url and the title extracted from header of the given url
        """
        self.browser.open(url, timeout=TIMEOUT)
        return (
            str(self.browser.url),
            str(self.browser.find("head").find("title").string),
        )


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
    ]

    scraper: Scraper
    favicon_downloader: FaviconDownloader

    def __init__(
        self,
        scraper: Scraper = Scraper(),
        favicon_downloader: FaviconDownloader = FaviconDownloader(),
    ) -> None:
        self.scraper = scraper
        self.favicon_downloader = favicon_downloader

    def _fix_url(self, url: str) -> str:
        """Return a url with https scheme if the scheme is originally missing from it"""
        if not url.startswith("http"):
            return f"https:{url}"
        return url

    def _get_favicon_smallest_dimension(self, content: bytes) -> int:
        """Return the smallest of the favicon image width and height"""
        with Image.open(BytesIO(content)) as img:
            width, height = img.size
            return int(min(width, height))

    def _extract_favicons(self, url: str) -> list[dict[str, Any]]:
        """Extract all favicons for a given url"""
        logger.info(f"Extracting favicons for {url}")
        favicons = []
        try:
            favicon_data: FaviconData = self.scraper.scrape_favicon_data(url)

            for favicon in favicon_data.links:
                favicon_url = favicon["href"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(favicon_data.url, favicon_url)
                favicons.append(favicon)

            for favicon in favicon_data.metas:
                favicon_url = favicon["content"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(favicon_data.url, favicon_url)
                else:
                    favicon["href"] = favicon_url
                favicons.append(favicon)

            # Some domains have a default "favicon.ico" in their root without explicitly
            # specifying them via rel attribute of link tag.
            default_favicon_url = self.scraper.get_default_favicon(url)
            if default_favicon_url is not None:
                favicons.append({"href": default_favicon_url})

        except Exception as e:
            logger.info(f"Exception {e} while extracting favicons for {url}")
            pass

        return favicons

    def _get_best_favicon(self, favicons: list[dict[str, Any]], min_width: int) -> str:
        """Return the favicon with the highest resolution that satisfies the minimum width
        criteria from a list of favicons.
        """
        best_favicon_url = ""
        best_favicon_width = 0
        for favicon in favicons:
            url = self._fix_url(favicon["href"])
            width = None
            sizes = favicon.get("sizes")
            if sizes:
                try:
                    width = int(sizes.split("x")[0])
                except Exception as e:
                    logger.info(
                        f"{e} while deducing size from sizes attribute of favicon {favicon}"
                    )
                    pass
            if width is None:
                try:
                    favicon_image: FaviconImage = (
                        self.favicon_downloader.download_favicon(url)
                    )

                    # If it is an SVG, then return this as the best favicon because SVG favicons
                    # are scalable, can be printed with high quality at any resolution and SVG
                    # graphics do NOT lose any quality if they are zoomed or resized.
                    if favicon_image.content_type == "image/svg+xml":
                        # Firefox doesn't support masked favicons yet. Return if not masked.
                        if "mask" not in favicon:
                            return url
                        else:
                            logger.info(
                                f"Masked SVG favicon {favicon} found; skipping it"
                            )
                            continue

                    width = self._get_favicon_smallest_dimension(favicon_image.content)
                except Exception as e:
                    logger.info(f"Exception {e} for favicon {favicon}")
                    pass
            if width and width > best_favicon_width:
                best_favicon_url = url
                best_favicon_width = width

        logger.debug(f"best favicon url:{best_favicon_url}, width:{best_favicon_width}")

        return best_favicon_url if best_favicon_width >= min_width else ""

    def get_favicons(
        self, domains_data: list[dict[str, Any]], min_width: int
    ) -> list[str]:
        """Extract favicons for each domain and return the one that satisfies the minimum width
        criteria for each domain. If multiple favicons satisfy the criteria then return the one
        with the highest resolution.
        """
        result = []
        for domain_data in domains_data:
            domain = domain_data["domain"]
            url = f"https://{domain}"
            favicons = self._extract_favicons(url)
            if len(favicons) == 0 and "www." not in domain:
                # Retry with www. in the domain as some domains require it explicitly.
                url = f"https://www.{domain}"
                favicons = self._extract_favicons(url)

            logger.info(
                f"{len(favicons)} favicons extracted for {url}. Favicons are: {favicons}"
            )
            best_favicon = self._get_best_favicon(favicons, min_width)
            result.append(best_favicon)
        return result

    def _extract_url_and_title(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract title and the final redirected base url for a given url"""
        logger.info(f"Extracting title for {url}")
        title = None
        final_redirected_base_url = None
        try:
            final_redirected_url, title = self.scraper.scrape_url_and_title(url)
            parsed_url = urlparse(final_redirected_url)
            final_redirected_base_url = f"{parsed_url.scheme}://{parsed_url.hostname}"
            title = " ".join(title.split())
        except Exception as e:
            logger.info(f"Exception: {e} while extracting title from document")
            pass

        title = (
            title
            if title
            and not [t for t in self.INVALID_TITLES if t.casefold() in title.casefold()]
            else None
        )
        return (final_redirected_base_url, title)

    def get_urls_and_titles(
        self, domains_data: list[dict[str, Any]]
    ) -> list[dict[str, Optional[str]]]:
        """Extract title and final redirected base url of each domain"""
        result = []
        for domain_data in domains_data:
            domain = domain_data["domain"]
            url = f"https://{domain}"
            final_redirected_base_url, title = self._extract_url_and_title(url)
            if title is None and "www." not in domain:
                # Retry with www. in the domain as some domains require it explicitly.
                url = f"https://www.{domain}"
                final_redirected_base_url, title = self._extract_url_and_title(url)

            # if no valid title is present then fallback to use the second level domain as title
            if title is None:
                title = self._get_second_level_domain(domain_data)
                title = title.capitalize()

            logger.info(f"url {final_redirected_base_url} and title {title}")
            result.append({"url": final_redirected_base_url, "title": title})

        return result

    def _get_second_level_domain(self, domain_data: dict[str, Any]) -> str:
        """Extract the second level domain for a given domain"""
        domain = domain_data["domain"]
        top_level_domain = domain_data["suffix"]
        second_level_domain = str(domain.replace("." + top_level_domain, ""))
        return second_level_domain

    def get_second_level_domains(self, domains_data: list[dict[str, Any]]) -> list[str]:
        """Extract the second level domain for each domain in the list"""
        return [
            self._get_second_level_domain(domain_data) for domain_data in domains_data
        ]
