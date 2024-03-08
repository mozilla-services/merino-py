"""Extract domain metadata from domain data"""
import logging
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel
from robobrowser import RoboBrowser

from merino.content_handler.models import Image
from merino.jobs.navigational_suggestions.utils import (
    REQUEST_HEADERS,
    TIMEOUT,
    FaviconDownloader,
    requests_get,
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
    META_SELECTOR: str = (
        "meta[name=apple-touch-icon], meta[name=msapplication-TileImage]"
    )
    MANIFEST_SELECTOR: str = 'link[rel="manifest"]'

    browser: RoboBrowser

    def __init__(self) -> None:
        session: requests.Session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        self.browser = RoboBrowser(
            session=session, parser="html.parser", allow_redirects=True
        )

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

    def scrape_favicons_from_manifest(self, manifest_url: str) -> list[dict[str, Any]]:
        """Scrape favicons from manifest of an already opened URL.

        Args:
            manifest_url: URL of the manifest file
        Returns:
            list[str]: URLs of the scraped favicons
        """
        result = []
        try:
            response: Optional[requests.Response] = requests_get(manifest_url)
            if response:
                result = response.json().get("icons")
        except Exception as e:
            logger.info(
                f"Exception: {e} while parsing icons from manifest {manifest_url}"
            )
        return result

    def get_default_favicon(self, url: str) -> Optional[str]:
        """Return the default favicon for the given url.

        Args:
            url: URL to scrape for favicon at default location
        Returns:
            Optional[str]: Default favicon url if it exists
        """
        try:
            default_favicon_url: str = urljoin(url, "favicon.ico")
            response: Optional[requests.Response] = requests_get(default_favicon_url)
            return response.url if response else None
        except Exception as e:
            logger.info(
                f"Exception: {e} while getting default favicon {default_favicon_url}"
            )
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
    favicon_downloader: FaviconDownloader

    def __init__(
        self,
        blocked_domains: set[str],
        scraper: Scraper = Scraper(),
        favicon_downloader: FaviconDownloader = FaviconDownloader(),
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
        if not url.startswith("http"):
            return f"https:{url}"
        return url

    def _get_favicon_smallest_dimension(self, image: Image) -> int:
        """Return the smallest of the favicon image width and height"""
        width, height = image.open()
        return int(min(width, height))

    def _extract_favicons(self, scraped_url: str) -> list[dict[str, Any]]:
        """Extract all favicons for an already opened url"""
        logger.info(f"Extracting all favicons for {scraped_url}")
        favicons: list[dict[str, Any]] = []
        try:
            favicon_data: FaviconData = self.scraper.scrape_favicon_data(scraped_url)

            for favicon in favicon_data.links:
                favicon_url = favicon["href"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                favicons.append(favicon)

            for favicon in favicon_data.metas:
                favicon_url = favicon["content"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(scraped_url, favicon_url)
                else:
                    favicon["href"] = favicon_url
                favicons.append(favicon)

            for manifest in favicon_data.manifests:
                manifest_url: str = str(manifest.get("href"))
                manifest_absolute_url: str = urljoin(scraped_url, manifest_url)
                scraped_favicons: list[
                    dict[str, Any]
                ] = self.scraper.scrape_favicons_from_manifest(manifest_absolute_url)
                for scraped_favicon in scraped_favicons:
                    favicon_url = urljoin(
                        manifest_absolute_url, scraped_favicon.get("src")
                    )
                    favicons.append({"href": favicon_url})

            # Include the default "favicon.ico" if it exists in domain root
            default_favicon_url = self.scraper.get_default_favicon(scraped_url)
            if default_favicon_url is not None:
                favicons.append({"href": default_favicon_url})

        except Exception as e:
            logger.info(f"Exception {e} while extracting favicons for {scraped_url}")
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
            favicon_image: Image | None = self.favicon_downloader.download_favicon(url)
            if favicon_image is None:
                continue

            if "image/" not in favicon_image.content_type:
                # If favicon mime type is not "image" then skip it
                continue

            # If favicon is an SVG, then return this as the best favicon because SVG favicons
            # are scalable, can be printed with high quality at any resolution and SVG
            # graphics do NOT lose any quality if they are zoomed or resized.
            if favicon_image.content_type == "image/svg+xml":
                # Firefox doesn't support masked favicons yet. Return if not masked.
                if "mask" not in favicon:
                    return url
                else:
                    logger.info(f"Masked SVG favicon {favicon} found; skipping it")
                    continue
            try:
                width = self._get_favicon_smallest_dimension(favicon_image)
            except Exception as e:
                logger.info(f"Exception {e} for favicon {favicon}")

            if width and width > best_favicon_width:
                best_favicon_url = url
                best_favicon_width = width

        logger.debug(f"best favicon url:{best_favicon_url}, width:{best_favicon_width}")

        return best_favicon_url if best_favicon_width >= min_width else ""

    def _get_favicon(self, scraped_url: str, min_width: int) -> str:
        """Extract all favicons for an already opened URL and return the one that satisfies the
        minimum width criteria. If multiple favicons satisfy the criteria then return the one
        with the highest resolution.
        """
        favicons: list[dict[str, Any]] = self._extract_favicons(scraped_url)
        logger.info(
            f"{len(favicons)} favicons extracted for {scraped_url}. Favicons are: {favicons}"
        )
        return self._get_best_favicon(favicons, min_width)

    def _extract_title(self) -> Optional[str]:
        """Extract title for a url"""
        title: Optional[str] = self.scraper.scrape_title()
        if title:
            title = " ".join(title.split())
            title = (
                title
                if title
                and not [
                    t for t in self.INVALID_TITLES if t.casefold() in title.casefold()
                ]
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
        """Extract domain metadata for each domain"""
        result: list[dict[str, Optional[str]]] = []
        for domain_data in domains_data:
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
                    favicon = self._get_favicon(scraped_base_url, favicon_min_width)
                    second_level_domain = self._get_second_level_domain(domain, suffix)
                    title = self._get_title(second_level_domain)

            result.append(
                {
                    "url": scraped_base_url,
                    "title": title,
                    "icon": favicon,
                    "domain": second_level_domain,
                }
            )
        return result
