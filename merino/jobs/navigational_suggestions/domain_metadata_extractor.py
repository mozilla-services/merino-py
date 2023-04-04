import logging
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin

import requests
from PIL import Image
from robobrowser import RoboBrowser

logger = logging.getLogger(__name__)


class DomainMetadataExtractor:
    """Extract domain metadata from the domain data"""

    LINK_SELECTOR = 'link[rel=apple-touch-icon], link[rel=apple-touch-icon-precomposed], link[rel="icon shortcut"], link[rel="shortcut icon"], link[rel="icon"], link[rel="SHORTCUT ICON"], link[rel="fluid-icon"]'
    META_SELECTOR = "meta[name=apple-touch-icon]"
    FIREFOX_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:58.0) Gecko/20100101 Firefox/58.0"
    TIMEOUT = 60
    # A non-exhaustive list of substrings of invalid titles
    INVALID_TITLES = [
        "Attention Required",
        "Access denied",
        "Access Denied",
        "Access to this page has been denied",
        "Loading…",
        "Page loading",
    ]

    browser: RoboBrowser

    def __init__(self) -> None:
        self.browser = RoboBrowser(user_agent=self.FIREFOX_UA, parser="html.parser")

    def _fix_url(self, url: str) -> str:
        if not url.startswith("http"):
            return f"https:{url}"
        return url

    def _get_default_favicon(self, url: str) -> Optional[str]:
        default_favicon_url = f"{url}/favicon.ico"
        response = requests.get(
            url, headers={"User-agent": self.FIREFOX_UA}, timeout=self.TIMEOUT
        )
        return default_favicon_url if response.status_code == 200 else None

    def _extract_favicons(self, url: str) -> list[str]:
        logger.info(f"Extracting favicons for {url}")
        favicons = []
        try:
            self.browser.open(url, timeout=self.TIMEOUT)

            for link in self.browser.select(self.LINK_SELECTOR):
                favicon = link.attrs
                favicon_url = favicon["href"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(self.browser.url, favicon_url)
                favicons.append(favicon)

            for meta in self.browser.select(self.META_SELECTOR):
                favicon = meta.attrs
                favicon_url = favicon["content"]
                if favicon_url.startswith("data:"):
                    continue
                if not favicon_url.startswith("http") and not favicon_url.startswith(
                    "//"
                ):
                    favicon["href"] = urljoin(self.browser.url, favicon_url)
                else:
                    favicon["href"] = favicon_url
                favicons.append(favicon)

            # Some domains have a default "favicon.ico" in their root without explicitly
            # specifying them via rel attribute of link tag.
            default_favicon_url = self._get_default_favicon(url)
            if default_favicon_url is not None:
                favicons.append({"href": default_favicon_url})

        except Exception as e:
            logger.info(f"Exception {str(e)} while extracting favicons for {url}")
            pass

        return favicons

    def _get_best_favicon(self, favicons: list[str]) -> str:
        best_favicon_url = None
        best_favicon_width = 0
        for favicon in favicons:
            url = self._fix_url(favicon.get("href"))
            width = None
            sizes = favicon.get("sizes")
            if sizes:
                try:
                    width = int(sizes.split("x")[0])
                except:
                    pass
            if width is None:
                try:
                    response = requests.get(
                        url,
                        headers={"User-agent": self.FIREFOX_UA},
                        timeout=self.TIMEOUT,
                    )

                    # If it is an SVG, then return this as the best favicon because SVG favicons
                    # are scalable, can be printed with high quality at any resolution and SVG
                    # graphics do NOT lose any quality if they are zoomed or resized.
                    if response.headers.get("Content-Type") == "image/svg+xml":
                        # Firefox doesn't support masked favicons yet. Return if not masked.
                        if "mask" not in favicon:
                            return url
                        else:
                            logger.info(f"Masked SVG favicon {favicon} found")
                            continue

                    with Image.open(BytesIO(response.content)) as img:
                        width, height = img.size
                        if width != height:
                            logger.info(
                                f'favicon shape "{width}*{height}" is not square'
                            )
                            width = min(width, height)
                except Exception as e:
                    logger.info(
                        f'Exception "{str(e)}" while getting best favicon {url}'
                    )
                    pass
            if width and width > best_favicon_width:
                best_favicon_url = url
                best_favicon_width = width

        return best_favicon_url

    def get_favicons(self, domains_data: list[dict]) -> list[str]:
        """Extract favicons for domains and return the one with highest resolution for each domain"""
        result = []
        for domain_data in domains_data:
            domain = domain_data["domain"]
            url = f"https://{domain}"
            favicons = self._extract_favicons(url)
            if len(favicons) == 0 and "www." not in domain:
                # Retry with www. in the domain as some domains require it explicitly.
                url = f"https://www.{domain}"
                favicons = self._extract_favicons(url)

            best_favicon = self._get_best_favicon(favicons)
            result.append(best_favicon)
        return result

    def _extract_title(self, url: str) -> Optional[str]:
        logger.info(f"Extracting titles for {url}")
        titles = []
        try:
            self.browser.open(url, timeout=self.TIMEOUT)
            titles = [title.text for title in self.browser.select("title")]
        except Exception as e:
            logger.info(f"Exception: {str(e)} while extracting titles from document")
            pass

        return (
            titles[0]
            if len(titles) > 0
            and not any(map(titles[0].__contains__, self.INVALID_TITLES))
            else None
        )

    def get_urls_and_titles(self, domains_data: list[dict]) -> list[dict]:
        """Extract title of each domain"""
        result = []
        for domain_data in domains_data:
            domain = domain_data["domain"]
            url = f"https://{domain}"
            title = self._extract_title(url)
            if title is None and "www." not in domain:
                # Retry with www. in the domain as some domains require it explicitly.
                url = f"https://www.{domain}"
                title = self._extract_title(url)

            # if no valid title is present then fallback to use the second level domain as title
            if title is None:
                title = self._get_second_level_domain(domain_data)

            result.append({"url": url, "title": title})

        return result

    def _get_second_level_domain(self, domain_data: dict) -> str:
        domain = domain_data["domain"]
        top_level_domain = domain_data["suffix"]
        second_level_domain = domain.replace("." + top_level_domain, "")
        return second_level_domain

    def get_second_level_domains(self, domains_data: list[dict]) -> list[str]:
        """Extract the second level domain"""
        return [
            self._get_second_level_domain(domain_data) for domain_data in domains_data
        ]
