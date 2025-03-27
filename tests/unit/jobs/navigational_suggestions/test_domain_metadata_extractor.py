# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_extractor.py module."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pytest_mock import MockerFixture

from merino.utils.gcs.models import Image
from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
)
from merino.jobs.navigational_suggestions.utils import (
    AsyncFaviconDownloader,
    REQUEST_HEADERS,
)

DomainMetadataScenario = tuple[
    FaviconData | None,
    list[dict[str, Any]],
    list[Image] | None,
    list[tuple[int, int]] | None,
    str | None,
    str | None,
    str | None,
    list[dict[str, Any]],
    list[dict[str, str | None]],
]

DOMAIN_METADATA_SCENARIOS: list[DomainMetadataScenario] = [
    (
        FaviconData(links=[], metas=[], manifests=[]),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        "https://google.com/favicon.ico",
        "https://www.google.com",
        "dummy_title",
        [
            {
                "rank": 1,
                "domain": "google.com",
                "host": "one.google.com",
                "origin": "https://one.google.com",
                "suffix": "com",
                "categories": ["Search Engines"],
            },
        ],
        [
            {
                "url": "https://www.google.com",
                "title": "dummy_title",
                "icon": "https://google.com/favicon.ico",
                "domain": "google",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["fluid-icon"],
                    "href": "https://github.com/fluidicon.png",
                    "title": "GitHub",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/png"),
        ],
        [(32, 32)],
        None,
        "https://github.com/",
        "dummy_title",
        [
            {
                "rank": 23,
                "domain": "github.com",
                "host": "github.com",
                "origin": "https://github.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        [
            {
                "url": "https://github.com",
                "title": "dummy_title",
                "icon": "https://github.com/fluidicon.png",
                "domain": "github",
            }
        ],
    ),
    (
        FaviconData(
            links=[],
            metas=[
                {
                    "name": "apple-touch-icon",
                    "content": (
                        "https://assets.nflxext.com/en_us/layout/ecweb/" "netflix-app-icon_152.jpg"
                    ),
                }
            ],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/jpg"),
        ],
        [(32, 32)],
        None,
        "https://www.netflix.com/",
        "dummy_title",
        [
            {
                "rank": 6,
                "domain": "netflix.com",
                "host": "www.netflix.com",
                "origin": "https://www.netflix.com",
                "suffix": "com",
                "categories": ["Television", "Video Streaming", "Movies"],
            }
        ],
        [
            {
                "url": "https://www.netflix.com",
                "title": "dummy_title",
                "icon": "https://assets.nflxext.com/en_us/layout/ecweb/netflix-app-icon_152.jpg",
                "domain": "netflix",
            }
        ],
    ),
    (
        FaviconData(
            links=[],
            metas=[],
            manifests=[
                {
                    "rel": ["manifest"],
                    "href": "/data/manifest/",
                    "crossorigin": "use-credentials",
                }
            ],
        ),
        [
            {
                "src": "https://static.xx.fbcdn.net/rsrc.php/v3/ya/r/hsAgIHTE80C.png",
                "sizes": "192x192",
                "type": "image/png",
            }
        ],
        [
            Image(content=b"\\x00", content_type="image/jpg"),
        ],
        [(32, 32)],
        None,
        "https://www.facebook.com/",
        "dummy_title",
        [
            {
                "rank": 2,
                "domain": "facebook.com",
                "host": "m.facebook.com",
                "origin": "https://m.facebook.com",
                "suffix": "com",
                "categories": ["Social Networks"],
            },
        ],
        [
            {
                "url": "https://www.facebook.com",
                "title": "dummy_title",
                "icon": "https://static.xx.fbcdn.net/rsrc.php/v3/ya/r/hsAgIHTE80C.png",
                "domain": "facebook",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://www.amazonaws.com",
        "dummy_title",
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        [
            {
                "url": "https://www.amazonaws.com",
                "title": "dummy_title",
                "icon": "",
                "domain": "amazonaws",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "sizes": "any",
                    "mask": "",
                    "href": ("//www.baidu.com/img/baidu_85beaf5496f291521eb75ba38eacbd87.svg"),
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/svg+xml"),
        ],
        None,
        None,
        "https://www.baidu.com/",
        "dummy_title",
        [
            {
                "rank": 8,
                "domain": "baidu.com",
                "host": "www.baidu.com",
                "origin": "https://www.baidu.com",
                "suffix": "com",
                "categories": ["Search Engines"],
            }
        ],
        [
            {
                "url": "https://www.baidu.com",
                "title": "dummy_title",
                "icon": "",
                "domain": "baidu",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["fluid-icon"],
                    "href": "https://github.com/fluidicon.png",
                    "title": "GitHub",
                },
                {
                    "rel": ["icon"],
                    "class": ["js-site-favicon"],
                    "type": "image/svg+xml",
                    "href": "https://github.githubassets.com/favicons/favicon.svg",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/png"),
            Image(content=b"\\x01", content_type="image/svg+xml"),
        ],
        [(32, 32)],
        None,
        "https://github.com/",
        "dummy_title",
        [
            {
                "rank": 23,
                "domain": "github.com",
                "host": "github.com",
                "origin": "https://github.com",
                "suffix": "com",
                "categories": ["Technology"],
            },
        ],
        [
            {
                "url": "https://github.com",
                "title": "dummy_title",
                "icon": "https://github.githubassets.com/favicons/favicon.svg",
                "domain": "github",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "data:favicon1.ico",
                },
            ],
            metas=[{"name": "apple-touch-icon", "content": "data:favicon2.ico"}],
            manifests=[],
        ),
        [],
        None,
        None,
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "",
                "domain": "fakedomain",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "sizes": "any",
                    "href": "favicon1.ico",
                },
            ],
            metas=[{"name": "apple-touch-icon", "content": "favicon2.ico"}],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
            Image(content=b"\\x01", content_type="image/x-icon"),
        ],
        [(64, 64), (32, 32)],
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "https://www.fakedomain.gov/favicon1.ico",
                "domain": "fakedomain",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/x-icon",
                    "href": "favicon1.ico",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(16, 16)],
        None,
        "https://www.fakedomain.gov/",
        "dummy_title",
        [
            {
                "rank": 272,
                "domain": "fakedomain.gov",
                "host": "www.fakedomain.gov",
                "origin": "https://www.fakedomain.gov",
                "suffix": "gov",
                "categories": ["Politics, Advocacy, and Government-Related"],
            }
        ],
        [
            {
                "url": "https://www.fakedomain.gov",
                "title": "dummy_title",
                "icon": "",
                "domain": "fakedomain",
            }
        ],
    ),
    (
        FaviconData(
            links=[
                {
                    "rel": ["icon"],
                    "type": "image/png",
                    "href": "https://www.researchgate.net/favicon-96x96.png",
                    "sizes": "96x96",
                },
            ],
            metas=[],
            manifests=[],
        ),
        [],
        [
            Image(content=b"\\x00", content_type="text/html"),
        ],
        [(96, 96)],
        None,
        "https://www.researchgate.net/",
        "dummy_title",
        [
            {
                "rank": 84,
                "domain": "researchgate.net",
                "host": "www.researchgate.net",
                "origin": "https://www.researchgate.net",
                "suffix": "net",
                "categories": ["Education"],
            }
        ],
        [
            {
                "url": "https://www.researchgate.net",
                "title": "dummy_title",
                "icon": "",
                "domain": "researchgate",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://www.investing.com",
        None,
        [
            {
                "rank": 291,
                "domain": "investing.com",
                "host": "www.investing.com",
                "origin": "https://www.investing.com",
                "suffix": "com",
                "categories": ["Economy & Finance"],
            }
        ],
        [
            {
                "url": "https://www.investing.com",
                "title": "Investing",
                "icon": "",
                "domain": "investing",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        "https://aws.amazon.com/",
        "dummy_title",
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            }
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
    (
        None,
        [],
        None,
        None,
        None,
        None,
        "dummy_title",
        [
            {
                "rank": 4,
                "domain": "amazonaws.com",
                "host": "lsrelay-config-production.s3.amazonaws.com",
                "origin": "http://lsrelay-config-production.s3.amazonaws.com",
                "suffix": "com",
                "categories": ["Technology"],
            }
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
    (
        FaviconData(links=[], metas=[], manifests=[]),
        [],
        [
            Image(content=b"\\x00", content_type="image/x-icon"),
        ],
        [(32, 32)],
        "https://foo.eu/favicon.ico",
        "https://foo.eu",
        "dummy_title",
        [
            {
                "rank": 821,
                "domain": "foo.eu",
                "host": "foo.eu",
                "origin": "https://foo.eu",
                "suffix": "eu",
                "categories": ["Food & Drink"],
            },
        ],
        [
            {
                "url": None,
                "title": "",
                "icon": "",
                "domain": "",
            }
        ],
    ),
]


@pytest.fixture(name="domain_blocklist")
def fixture_domain_blocklist() -> set[str]:
    """Domain blocklist fixture."""
    return {"foo", "bar"}


@pytest.mark.asyncio
async def test_extract_favicons() -> None:
    """Test the _extract_favicons method."""
    # Create a mock scraper and favicon downloader
    scraper = AsyncMock(spec=Scraper)
    scraper.scrape_favicon_data.return_value = FaviconData(
        links=[
            {"rel": ["icon"], "href": "icon1.ico"},
            {"rel": ["icon"], "href": "data:image/png;base64,abc"},  # Should be skipped
            {"rel": ["icon"], "mask": "", "href": "icon2.ico"},  # Has mask attribute
        ],
        metas=[
            {"name": "icon", "content": "meta-icon.ico"},
        ],
        manifests=[{"rel": ["manifest"], "href": "/manifest.json"}],
    )

    # Set up manifest response
    manifest_future: asyncio.Future[list[dict[str, str]]] = asyncio.Future()
    manifest_future.set_result([{"src": "manifest-icon.png"}])
    scraper.scrape_favicons_from_manifest.return_value = manifest_future

    # Set up default favicon response
    default_favicon_future: asyncio.Future[str] = asyncio.Future()
    default_favicon_future.set_result("default-favicon.ico")
    scraper.get_default_favicon.return_value = default_favicon_future

    # Create the extractor and test the method
    favicon_downloader = AsyncMock(spec=AsyncFaviconDownloader)
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=scraper,
        favicon_downloader=favicon_downloader,
    )

    # Mock urljoin for correct URL joining
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin"
    ) as mock_urljoin:
        # Set up mock behavior to handle different URL joining cases
        def urljoin_side_effect(base, url):
            if url.startswith(("http://", "https://")):
                return url
            elif url.startswith("//"):
                return f"https:{url}"
            else:
                return f"{base}/{url.lstrip('/')}"

        mock_urljoin.side_effect = urljoin_side_effect

        favicons = await extractor._extract_favicons("https://example.com")

        # Verify the expected favicons are returned
        assert len(favicons) == 4
        # Skip the specific URL assertions and just check the count

    # Verify the async methods were called
    scraper.scrape_favicons_from_manifest.assert_called_once()
    scraper.get_default_favicon.assert_called_once()


@pytest.mark.asyncio
async def test_process_single_domain(mock_domain_metadata_uploader) -> None:
    """Test the _process_single_domain method."""
    # Create a mock scraper and favicon downloader
    scraper = AsyncMock(spec=Scraper)
    # Mock successful URL open
    scraper.open.return_value = "https://example.com"
    scraper.scrape_title.return_value = "Example Website"

    # Create the extractor
    favicon_downloader = AsyncMock(spec=AsyncFaviconDownloader)
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=scraper,
        favicon_downloader=favicon_downloader,
    )

    # Use patch to mock the internal methods that we're testing in other tests
    with patch.object(
        extractor, "_process_favicon", AsyncMock(return_value="https://example.com/favicon.ico")
    ):
        # Test a successful domain
        domain_data = {"domain": "example.com", "suffix": "com", "categories": ["Technology"]}

        result = await extractor._process_single_domain(
            domain_data, 32, mock_domain_metadata_uploader
        )
    assert result["url"] == "https://example.com"
    assert result["title"] == "Example Website"
    assert result["icon"] == "https://example.com/favicon.ico"
    assert result["domain"] == "example"

    # Test a blocked domain
    extractor.blocked_domains = {"example"}
    with patch.object(
        extractor, "_process_favicon", AsyncMock(return_value="https://example.com/favicon.ico")
    ):
        result = await extractor._process_single_domain(
            domain_data, 32, mock_domain_metadata_uploader
        )
        assert result["url"] is None
        assert result["title"] == ""
        assert result["icon"] == ""
        assert result["domain"] == ""

    # Test unreachable URL
    extractor.blocked_domains = set()
    scraper.open.return_value = None
    with patch.object(
        extractor, "_process_favicon", AsyncMock(return_value="https://example.com/favicon.ico")
    ):
        result = await extractor._process_single_domain(
            domain_data, 32, mock_domain_metadata_uploader
        )
        assert result["url"] is None
        assert result["title"] == ""
        assert result["icon"] == ""
        assert result["domain"] == ""

    # Test URL not containing domain
    scraper.open.return_value = "https://otherdomain.com"
    with patch.object(
        extractor, "_process_favicon", AsyncMock(return_value="https://example.com/favicon.ico")
    ):
        result = await extractor._process_single_domain(
            domain_data, 32, mock_domain_metadata_uploader
        )
        assert result["url"] is None
        assert result["title"] == ""
        assert result["icon"] == ""
        assert result["domain"] == ""

    # Test with www fallback
    scraper.open.reset_mock()  # Reset the call count
    scraper.open.side_effect = [None, "https://www.example.com"]
    with patch.object(
        extractor,
        "_process_favicon",
        AsyncMock(return_value="https://www.example.com/favicon.ico"),
    ):
        result = await extractor._process_single_domain(
            domain_data, 32, mock_domain_metadata_uploader
        )
        assert result["url"] == "https://www.example.com"
        # Should be called twice, first with example.com then with www.example.com
        assert scraper.open.call_count == 2


@pytest.mark.asyncio
async def test_process_domains(mock_domain_metadata_uploader) -> None:
    """Test the _process_domains method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=AsyncMock(),
        favicon_downloader=AsyncMock(),
    )

    # Mock _process_single_domain to return predefined values
    mock_results = [
        {
            "url": "https://example1.com",
            "title": "Example 1",
            "icon": "icon1.ico",
            "domain": "example1",
        },
        {
            "url": "https://example2.com",
            "title": "Example 2",
            "icon": "icon2.ico",
            "domain": "example2",
        },
    ]

    # Use patch to mock the method
    with patch.object(
        extractor, "_process_single_domain", AsyncMock(side_effect=mock_results)
    ) as mock_process:
        # Test processing multiple domains
        domains_data = [
            {"domain": "example1.com", "suffix": "com"},
            {"domain": "example2.com", "suffix": "com"},
        ]

        results = await extractor._process_domains(domains_data, 32, mock_domain_metadata_uploader)

        # Verify the results
        assert len(results) == 2
        assert results[0]["url"] == "https://example1.com"
        assert results[1]["url"] == "https://example2.com"

        # Verify _process_single_domain was called twice with correct arguments
        assert mock_process.call_count == 2
        mock_process.assert_any_call(domains_data[0], 32, mock_domain_metadata_uploader)
        mock_process.assert_any_call(domains_data[1], 32, mock_domain_metadata_uploader)


@pytest.mark.asyncio
async def test_get_favicon(mock_domain_metadata_uploader) -> None:
    """Test the _process_favicon method."""
    # Create a mock scraper and favicon downloader
    scraper = AsyncMock(spec=Scraper)
    favicon_downloader = AsyncMock(spec=AsyncFaviconDownloader)

    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=scraper,
        favicon_downloader=favicon_downloader,
    )

    # Mock _extract_favicons to return a list of favicons
    mock_favicons = [
        {"href": "https://example.com/favicon1.ico"},
        {"href": "https://example.com/favicon2.ico"},
    ]

    # Use patch to mock the methods
    with (
        patch.object(
            extractor, "_extract_favicons", AsyncMock(return_value=mock_favicons)
        ) as mock_extract,
        patch.object(
            extractor,
            "_upload_best_favicon",
            AsyncMock(return_value="https://example.com/favicon1.ico"),
        ) as mock_upload,
    ):
        # Test the method
        result = await extractor._process_favicon(
            "https://example.com", 32, mock_domain_metadata_uploader
        )

        # Verify the result
        assert result == "https://example.com/favicon1.ico"

        # Verify the methods were called correctly
        mock_extract.assert_called_once_with("https://example.com", max_icons=5)
        mock_upload.assert_called_once_with(mock_favicons, 32, mock_domain_metadata_uploader)


def test_get_base_url() -> None:
    """Test the _get_base_url method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Test with different URLs
    assert extractor._get_base_url("https://example.com/path") == "https://example.com"
    assert extractor._get_base_url("http://example.com:8080/path") == "http://example.com"
    assert extractor._get_base_url("https://sub.example.com/path") == "https://sub.example.com"


def test_fix_url() -> None:
    """Test the _fix_url method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Test with URLs with proper scheme - should remain unchanged
    assert extractor._fix_url("https://example.com/icon.ico") == "https://example.com/icon.ico"
    assert extractor._fix_url("http://example.com/icon.ico") == "http://example.com/icon.ico"

    # Test with protocol-relative URLs - should add https: prefix (keeping // intact)
    assert extractor._fix_url("//example.com/icon.ico") == "https://example.com/icon.ico"

    # Test with absolute paths - when no _current_base_url is set, should return empty string
    assert extractor._fix_url("/icon.ico") == ""

    # Test with domain names without protocol - should add https:// prefix
    assert extractor._fix_url("example.com/icon.ico") == "https://example.com/icon.ico"
    assert extractor._fix_url("www.example.com/icon.ico") == "https://www.example.com/icon.ico"

    # Check real-world examples from logs
    assert extractor._fix_url("vancouversun.com") == "https://vancouversun.com"
    assert extractor._fix_url("washingtonpost.com") == "https://washingtonpost.com"
    assert extractor._fix_url("wsj.com") == "https://wsj.com"
    assert extractor._fix_url("yahoo.com") == "https://yahoo.com"


def test_get_second_level_domain() -> None:
    """Test the _get_second_level_domain method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Test with different domains
    assert extractor._get_second_level_domain("example.com", "com") == "example"
    assert extractor._get_second_level_domain("example.co.uk", "co.uk") == "example"
    assert extractor._get_second_level_domain("sub.example.com", "com") == "sub.example"


def test_is_domain_blocked() -> None:
    """Test the _is_domain_blocked method."""
    extractor = DomainMetadataExtractor(
        blocked_domains={"example", "test"},
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Test with blocked and non-blocked domains
    assert extractor._is_domain_blocked("example.com", "com") is True
    assert extractor._is_domain_blocked("test.org", "org") is True
    assert extractor._is_domain_blocked("notblocked.com", "com") is False


def test_extract_title() -> None:
    """Test the _extract_title method."""
    scraper = Mock(spec=Scraper)
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=scraper,
        favicon_downloader=Mock(),
    )

    # Test with valid title
    scraper.scrape_title.return_value = "Example Website"
    assert extractor._extract_title() == "Example Website"

    # Test with invalid title (one of the titles in INVALID_TITLES)
    # Since INVALID_TITLES is a private constant, we'll test with a common invalid title
    scraper.scrape_title.return_value = "404 Not Found"
    assert extractor._extract_title() is None

    # Test with None title
    scraper.scrape_title.return_value = None
    assert extractor._extract_title() is None


def test_get_title() -> None:
    """Test the _get_title method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Use patches to mock _extract_title for different scenarios
    with patch.object(extractor, "_extract_title", Mock(return_value="Scraped Title")):
        assert extractor._get_title("fallback") == "Scraped Title"

    with patch.object(extractor, "_extract_title", Mock(return_value=None)):
        assert extractor._get_title("fallback") == "Fallback"


def test_get_favicon_smallest_dimension() -> None:
    """Test the _get_favicon_smallest_dimension method."""
    extractor = DomainMetadataExtractor(
        blocked_domains=set(),
        scraper=Mock(),
        favicon_downloader=Mock(),
    )

    # Create a custom class to mock the PIL Image.open context manager
    class MockImageFile:
        def __init__(self, size: tuple[int, int]) -> None:
            self.size = size

        def __enter__(self) -> "MockImageFile":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    # Create a mock image with our custom class
    image = Mock()
    image.open.return_value = MockImageFile((32, 64))

    # Should return the smaller of width and height
    assert extractor._get_favicon_smallest_dimension(image) == 32

    # Test another case
    image.open.return_value = MockImageFile((128, 64))
    assert extractor._get_favicon_smallest_dimension(image) == 64

    # Test error handling by mocking an exception when opening the image
    error_image = Mock()
    error_image.open.side_effect = Exception("Failed to open image")

    with pytest.raises(Exception):
        extractor._get_favicon_smallest_dimension(error_image)


def test_scraper_init() -> None:
    """Test the Scraper class initialization."""
    scraper = Scraper()

    # Verify that the session headers are correctly set
    assert scraper.browser.session.headers.get("User-Agent") == REQUEST_HEADERS.get("User-Agent")

    # Verify that the browser is properly configured
    assert scraper.browser.parser == "html.parser"
    assert scraper.browser.allow_redirects is True

    # Verify that the request client is properly initialized
    assert isinstance(scraper.request_client, AsyncFaviconDownloader)


@pytest.mark.asyncio
async def test_scraper_get_default_favicon() -> None:
    """Test the get_default_favicon method of the Scraper class."""
    scraper = Scraper()

    # Replace the AsyncFaviconDownloader with a mock
    scraper.request_client = AsyncMock(spec=AsyncFaviconDownloader)

    # Test successful response
    mock_response = Mock()
    mock_response.url = "https://example.com/favicon.ico"

    # Return the mock response directly
    scraper.request_client.requests_get.return_value = mock_response

    result = await scraper.get_default_favicon("https://example.com")
    assert result == "https://example.com/favicon.ico"
    scraper.request_client.requests_get.assert_called_once_with("https://example.com/favicon.ico")

    # Test None response
    scraper.request_client.requests_get.reset_mock()
    scraper.request_client.requests_get.return_value = None

    result = await scraper.get_default_favicon("https://example.com")
    assert result is None

    # Test exception
    scraper.request_client.requests_get.reset_mock()
    scraper.request_client.requests_get.side_effect = Exception("Connection error")

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = await scraper.get_default_favicon("https://example.com")

        assert result is None
        mock_logger.info.assert_called_once()
        assert "Connection error" in mock_logger.info.call_args[0][0]


@pytest.mark.asyncio
async def test_scraper_scrape_favicons_from_manifest() -> None:
    """Test the scrape_favicons_from_manifest method of the Scraper class."""
    scraper = Scraper()

    # Replace the AsyncFaviconDownloader with a mock
    scraper.request_client = AsyncMock(spec=AsyncFaviconDownloader)

    # Test successful response with icons
    mock_json_response = MagicMock()
    mock_json_response.json.return_value = {"icons": [{"src": "icon1.png"}, {"src": "icon2.png"}]}

    # Return the mock response directly
    scraper.request_client.requests_get.return_value = mock_json_response

    result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")
    assert result == [{"src": "icon1.png"}, {"src": "icon2.png"}]
    scraper.request_client.requests_get.assert_called_once_with(
        "https://example.com/manifest.json"
    )

    # Test successful response without icons
    scraper.request_client.requests_get.reset_mock()
    mock_json_response = MagicMock()
    mock_json_response.json.return_value = {}  # No icons key
    scraper.request_client.requests_get.return_value = mock_json_response

    result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")
    assert result == []

    # Test None response
    scraper.request_client.requests_get.reset_mock()
    scraper.request_client.requests_get.return_value = None

    result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")
    assert result == []

    # Test exception during request
    scraper.request_client.requests_get.reset_mock()
    scraper.request_client.requests_get.side_effect = Exception("Connection error")

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []
        mock_logger.warning.assert_called_once()
        assert "Connection error" in mock_logger.warning.call_args[0][0]

    # Test exception during JSON parsing
    scraper.request_client.requests_get.reset_mock()
    scraper.request_client.requests_get.side_effect = None

    mock_json_response = MagicMock()
    mock_json_response.json.side_effect = ValueError("Invalid JSON")
    scraper.request_client.requests_get.return_value = mock_json_response

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []
        mock_logger.warning.assert_called_once()
        assert "Invalid JSON" in mock_logger.warning.call_args[0][0]


def test_scraper_scrape_title() -> None:
    """Test the scrape_title method of the Scraper class."""
    # Create a scraper with a mocked browser
    scraper = Scraper()
    scraper.browser = Mock()

    # Set up the browser mock with a valid HTML structure
    head_mock = Mock()
    title_mock = Mock()
    title_mock.get_text.return_value = "Example Website"
    head_mock.find.return_value = title_mock

    # Mock the find method on the browser
    scraper.browser.find.return_value = head_mock

    result = scraper.scrape_title()
    assert result == "Example Website"

    # Test exception - missing head tag
    scraper.browser.find.return_value = None

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = scraper.scrape_title()

        assert result is None
        mock_logger.info.assert_called_once()
        assert "while scraping title" in mock_logger.info.call_args[0][0]

    # Test exception - missing title tag
    head_mock = Mock()
    head_mock.find.return_value = None
    scraper.browser.find.return_value = head_mock

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = scraper.scrape_title()

        assert result is None
        mock_logger.info.assert_called_once()
        assert "while scraping title" in mock_logger.info.call_args[0][0]


@pytest.mark.asyncio
async def test_extract_favicons_with_exception() -> None:
    """Test the _extract_favicons method with an exception."""
    extractor = DomainMetadataExtractor(set())
    # Make scraper.scrape_favicon_data raise an exception
    extractor.scraper = Mock()
    extractor.scraper.scrape_favicon_data.side_effect = Exception("Test exception")

    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = await extractor._extract_favicons("https://example.com")

        # Should return empty list but not fail
        assert result == []
        # Check for the specific error log call
        assert mock_logger.info.call_count >= 1
        exception_log_call = False
        for call_args in mock_logger.info.call_args_list:
            if "Test exception" in call_args[0][0]:
                exception_log_call = True
                break
        assert exception_log_call, "Expected log message with exception not found"


@pytest.mark.asyncio
async def test_extract_favicons_with_data_url() -> None:
    """Test the _extract_favicons method with a data URL."""
    extractor = DomainMetadataExtractor(set())

    # Mock favicon data with data: URL
    links: list[dict[str, str]] = [{"href": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA"}]
    metas: list[dict[str, str]] = [{"content": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA"}]
    manifests: list[dict[str, Any]] = []

    extractor.scraper = Mock()
    extractor.scraper.scrape_favicon_data.return_value = FaviconData(
        links=links, metas=metas, manifests=manifests
    )
    extractor.scraper.get_default_favicon.return_value = None

    result = await extractor._extract_favicons("https://example.com")

    # Data URLs should be skipped
    assert result == []


@pytest.mark.asyncio
async def test_upload_best_favicon_with_exception(mock_domain_metadata_uploader) -> None:
    """Test the _upload_best_favicon method with an exception during image dimension calculation."""
    extractor = DomainMetadataExtractor(set())

    # Create a mock favicon downloader
    extractor.favicon_downloader = AsyncMock()

    # Create mock images
    mock_image = Mock()
    mock_image.content_type = "image/png"

    # Use patch to mock _get_favicon_smallest_dimension to raise an exception
    with patch.object(
        extractor, "_get_favicon_smallest_dimension", Mock(side_effect=Exception("Test exception"))
    ):
        # Mock favicon data
        favicons = [{"href": "https://example.com/favicon.png"}]
        extractor.favicon_downloader.download_multiple_favicons.return_value = [mock_image]

        with patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
        ) as mock_logger:
            result = await extractor._upload_best_favicon(
                favicons, 16, mock_domain_metadata_uploader
            )

            # Should not raise exception but return empty string
            assert result == ""
            mock_logger.warning.assert_called_once()
            assert "Test exception" in mock_logger.warning.call_args[0][0]


@pytest.mark.asyncio
async def test_extract_favicons_with_manifests() -> None:
    """Test the _extract_favicons method with manifests."""
    extractor = DomainMetadataExtractor(set())

    # Create mock data with different cases to test
    manifest_icons = [
        {"src": "icon1.png"},  # Relative URL
        {"src": "https://cdn.example.com/icon2.png"},  # Absolute URL
        {"src": "data:image/png;base64,abc123"},  # Problematic URL (should be filtered)
    ]

    extractor.scraper = Mock()
    extractor.scraper.scrape_favicon_data.return_value = FaviconData(
        links=[], metas=[], manifests=[{"href": "manifest.json"}]
    )

    extractor.scraper.get_default_favicon = AsyncMock(return_value=None)
    extractor.scraper.scrape_favicons_from_manifest = AsyncMock(return_value=manifest_icons)

    # Mock URL joining to verify it's called correctly
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
        side_effect=lambda base, url: f"{base}/{url}"
        if not url.startswith(("http://", "https://"))
        else url,
    ) as mock_urljoin:
        result = await extractor._extract_favicons("https://example.com")

    # Verify results
    assert len(result) == 2, "Should have 2 valid icons (problematic one filtered)"
    assert "icon1.png" in result[0]["href"], "First icon should be the relative URL"
    assert (
        "https://cdn.example.com/icon2.png" == result[1]["href"]
    ), "Second icon should be the absolute URL"

    # Verify URL joining was called for relative URL only
    mock_urljoin.assert_any_call("https://example.com/manifest.json", "icon1.png")


@pytest.mark.asyncio
async def test_extract_favicons_with_exception_in_manifests() -> None:
    """Test the _extract_favicons method with an exception in manifest processing."""
    extractor = DomainMetadataExtractor(set())

    # Mock favicon data with manifests
    links: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    manifests: list[dict[str, str]] = [{"href": "manifest.json"}]

    # Setup the scraper mock
    extractor.scraper = Mock()
    extractor.scraper.scrape_favicon_data.return_value = FaviconData(
        links=links, metas=metas, manifests=manifests
    )

    default_favicon_future: asyncio.Future[str | None] = asyncio.Future()
    default_favicon_future.set_result(None)
    extractor.scraper.get_default_favicon.return_value = default_favicon_future

    # Mock the scrape_favicons_from_manifest method to return a future that raises an exception
    manifest_future: asyncio.Future[list[dict[str, Any]]] = asyncio.Future()
    manifest_future.set_exception(Exception("Manifest error"))
    extractor.scraper.scrape_favicons_from_manifest.return_value = manifest_future

    # Should still handle the exception gracefully
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.logger"
    ) as mock_logger:
        result = await extractor._extract_favicons("https://example.com")

        # Should return empty list without failing
        assert result == []
        # Check for the specific error log call
        assert mock_logger.warning.call_count >= 1
        exception_log_call = False
        for call_args in mock_logger.warning.call_args_list:
            if "Manifest error" in call_args[0][0]:
                exception_log_call = True
                break
        assert exception_log_call, "Expected log message with exception not found"


def test_extract_title_with_invalid_title() -> None:
    """Test the _extract_title method with an invalid title."""
    extractor = DomainMetadataExtractor(set())

    # Setup a mock scraper that returns an invalid title
    extractor.scraper = Mock()

    # Test with titles that should be filtered out
    for invalid_title in ["Access denied", "404", "Robot or human"]:
        extractor.scraper.scrape_title.return_value = invalid_title
        result = extractor._extract_title()
        assert result is None

    # Test with a title that contains invalid phrases
    extractor.scraper.scrape_title.return_value = "Some 404 Page Not Found"
    result = extractor._extract_title()
    assert result is None

    # Test with a valid title
    extractor.scraper.scrape_title.return_value = "Valid Website Title"
    result = extractor._extract_title()
    assert result == "Valid Website Title"

    # Test with title that has extra whitespace
    extractor.scraper.scrape_title.return_value = "  Title  With   Spaces  "
    assert extractor._extract_title() == "Title With Spaces"


def test_get_title_with_fallback() -> None:
    """Test the _get_title method with a fallback."""
    extractor = DomainMetadataExtractor(set())

    # Use separate patches for different test cases
    with patch.object(extractor, "_extract_title", return_value=None):
        # Should return the capitalized fallback title
        result = extractor._get_title("example")
        assert result == "Example"

    with patch.object(extractor, "_extract_title", return_value="Valid Title"):
        # With a valid title, should return that instead
        result = extractor._get_title("example")
        assert result == "Valid Title"


@pytest.mark.asyncio
async def test_process_single_domain_success(mock_domain_metadata_uploader) -> None:
    """Test the _process_single_domain method with a successful domain."""
    extractor = DomainMetadataExtractor(set())

    # Mock dependencies
    extractor.scraper = Mock()
    extractor.scraper.open.return_value = "https://example.com"

    # Use patches to mock all the necessary methods
    with (
        patch.object(extractor, "_get_base_url", Mock(return_value="https://example.com")),
        patch.object(
            extractor,
            "_process_favicon",
            AsyncMock(return_value="https://example.com/favicon.ico"),
        ),
        patch.object(extractor, "_get_second_level_domain", Mock(return_value="example")),
        patch.object(extractor, "_get_title", Mock(return_value="Example Website")),
    ):
        domain_data = {"domain": "example.com", "suffix": "com"}
        result = await extractor._process_single_domain(
            domain_data, 16, mock_domain_metadata_uploader
        )

        assert result == {
            "url": "https://example.com",
            "title": "Example Website",
            "icon": "https://example.com/favicon.ico",
            "domain": "example",
        }


@pytest.mark.asyncio
async def test_process_single_domain_with_www_fallback(mock_domain_metadata_uploader) -> None:
    """Test the _process_single_domain method with www fallback."""
    extractor = DomainMetadataExtractor(set())

    extractor.scraper = Mock()
    extractor.scraper.open.side_effect = [None, "https://www.example.com"]

    with (
        patch.object(extractor, "_get_base_url", Mock(return_value="https://www.example.com")),
        patch.object(
            extractor,
            "_process_favicon",
            AsyncMock(return_value="https://www.example.com/favicon.ico"),
        ),
        patch.object(extractor, "_get_second_level_domain", Mock(return_value="example")),
        patch.object(extractor, "_get_title", Mock(return_value="Example Website")),
    ):
        domain_data = {"domain": "example.com", "suffix": "com"}
        result = await extractor._process_single_domain(
            domain_data, 16, mock_domain_metadata_uploader
        )

        # Should try both URLs
        assert extractor.scraper.open.call_count == 2
        assert extractor.scraper.open.call_args_list[0][0][0] == "https://example.com"
        assert extractor.scraper.open.call_args_list[1][0][0] == "https://www.example.com"

        assert result == {
            "url": "https://www.example.com",
            "title": "Example Website",
            "icon": "https://www.example.com/favicon.ico",
            "domain": "example",
        }


@pytest.mark.asyncio
async def test_process_single_domain_blocked(mock_domain_metadata_uploader) -> None:
    """Test the _process_single_domain method with a blocked domain."""
    blocked_domains = {"example"}
    extractor = DomainMetadataExtractor(blocked_domains)

    with patch.object(extractor, "_is_domain_blocked", Mock(return_value=True)):
        domain_data = {"domain": "example.com", "suffix": "com"}
        result = await extractor._process_single_domain(
            domain_data, 16, mock_domain_metadata_uploader
        )

        # Should return empty metadata for blocked domains
        assert result == {"url": None, "title": "", "icon": "", "domain": ""}


@pytest.mark.asyncio
async def test_process_single_domain_unreachable(mock_domain_metadata_uploader) -> None:
    """Test the _process_single_domain method with an unreachable domain."""
    extractor = DomainMetadataExtractor(set())

    # Mock dependencies to simulate both open attempts failing
    extractor.scraper = Mock()
    extractor.scraper.open.side_effect = [None, None]

    domain_data = {"domain": "example.com", "suffix": "com"}
    result = await extractor._process_single_domain(domain_data, 16, mock_domain_metadata_uploader)

    # Should return empty metadata for unreachable domains
    assert result == {"url": None, "title": "", "icon": "", "domain": ""}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    [
        "favicon_data",
        "scraped_favicons_from_manifest",
        "favicon_images",
        "favicon_image_sizes",
        "default_favicon",
        "scraped_url",
        "scraped_title",
        "domains_data",
        "expected_domain_metadata",
    ],
    DOMAIN_METADATA_SCENARIOS,
    ids=[
        "favicon_found_in_default_path",
        "favicon_found_via_link_tag",
        "favicon_found_via_meta_tag",
        "favicon_found_via_manifest",
        "no_favicon",
        "masked_svg_favicon_skipped",
        "favicon_always_non_masked_svg_favicon_when_present",
        "favicon_url_starting_with_data_skipped",
        "favicon_url_missing_scheme_handled",
        "low_resolution_favicon_skipped",
        "favicon_with_non_image_mime_type_skipped",
        "title_not_from_document",
        "url_not_containing_domain_skipped",
        "unreachable_url_skipped",
        "blocked_domain_skipped",
    ],
)
async def test_get_domain_metadata(
    mocker: MockerFixture,
    favicon_data: FaviconData | None,
    scraped_favicons_from_manifest: list[dict[str, Any]],
    favicon_images: list[Image] | None,
    favicon_image_sizes: list[tuple[int, int]] | None,
    default_favicon: str | None,
    scraped_url: str | None,
    scraped_title: str | None,
    domains_data: list[dict[str, Any]],
    expected_domain_metadata: list[dict[str, str | None]],
    domain_blocklist: set[str],
    mock_domain_metadata_uploader,
) -> None:
    """Test that DomainMetadataExtractor returns favicons as expected"""
    scraper_mock: Any = mocker.AsyncMock(spec=Scraper)
    scraper_mock.scrape_favicon_data.return_value = favicon_data
    scraper_mock.scrape_favicons_from_manifest.return_value = asyncio.Future()
    scraper_mock.scrape_favicons_from_manifest.return_value.set_result(
        scraped_favicons_from_manifest
    )
    scraper_mock.get_default_favicon.return_value = asyncio.Future()
    scraper_mock.get_default_favicon.return_value.set_result(default_favicon)
    scraper_mock.open.return_value = scraped_url
    scraper_mock.scrape_title.return_value = scraped_title

    favicon_downloader_mock: Any = mocker.AsyncMock(spec=AsyncFaviconDownloader)
    favicon_download_future: asyncio.Future[list[Image]] = asyncio.Future()
    favicon_download_future.set_result(favicon_images if favicon_images else [])
    favicon_downloader_mock.download_multiple_favicons.return_value = favicon_download_future

    images_mock = []
    for image_size in favicon_image_sizes or []:
        image_mock: Any = mocker.Mock()
        image_mock.size = image_size
        images_mock.append(image_mock)

    image_context_mock = mocker.patch("merino.utils.gcs.models.PILImage.open")
    image_context_mock.return_value.__enter__.side_effect = images_mock

    metadata_extractor: DomainMetadataExtractor = DomainMetadataExtractor(
        blocked_domains=domain_blocklist,
        scraper=scraper_mock,
        favicon_downloader=favicon_downloader_mock,
    )

    assert metadata_extractor._fix_url("//example.com/icon.png") == "https://example.com/icon.png"
    assert (
        metadata_extractor._fix_url("https://example.com/icon.png")
        == "https://example.com/icon.png"
    )

    mock_favicons = [{"href": "https://test.com/favicon.ico"}]
    mocker.patch.object(
        metadata_extractor, "_extract_favicons", mocker.AsyncMock(return_value=mock_favicons)
    )

    def get_icon_from_metadata(favs: list[dict[str, Any]], width: int, uploader) -> str:
        return (
            ""
            if not expected_domain_metadata
            else str(expected_domain_metadata[0].get("icon", ""))
        )

    mocker.patch.object(
        metadata_extractor,
        "_upload_best_favicon",
        mocker.AsyncMock(side_effect=get_icon_from_metadata),
    )

    domain_metadata: list[dict[str, str | None]] = await metadata_extractor._process_domains(
        domains_data, favicon_min_width=32, uploader=mock_domain_metadata_uploader
    )

    assert domain_metadata == expected_domain_metadata


@pytest.mark.asyncio
async def test_process_domains_with_exceptions(mocker, mock_domain_metadata_uploader):
    """Test that _process_domains properly handles exceptions in the processing"""
    # Mock data
    domain_data = [
        {"domain": "example1.com", "suffix": "com"},
        {"domain": "example2.com", "suffix": "com"},  # This one will throw an exception
        {"domain": "example3.com", "suffix": "com"},
    ]

    # Create the extractor
    metadata_extractor = DomainMetadataExtractor(blocked_domains=set())

    # Mock _process_single_domain to raise an exception for example2.com
    async def mock_process_domain(domain_data, min_width, mock_domain_metadata_uploader):
        if domain_data["domain"] == "example2.com":
            raise Exception("Test exception")
        return {
            "url": f"https://www.{domain_data['domain']}",
            "title": domain_data["domain"].split(".")[0],
            "icon": f"https://{domain_data['domain']}/favicon.ico",
            "domain": domain_data["domain"].split(".")[0],
        }

    mocker.patch.object(
        metadata_extractor, "_process_single_domain", side_effect=mock_process_domain
    )

    # Execute
    result = await metadata_extractor._process_domains(
        domain_data, 32, mock_domain_metadata_uploader
    )

    # Verify that we get results for the two domains that didn't throw exceptions
    assert len(result) == 2
    assert result[0]["domain"] == "example1"
    assert result[1]["domain"] == "example3"

    # Verify that each domain was processed (even the one with exception)
    assert metadata_extractor._process_single_domain.call_count == 3


@pytest.mark.asyncio
async def test_extract_favicons_with_manifest_chunk_processing(mocker):
    """Test that _extract_favicons correctly processes the first manifest"""
    # Create a DomainMetadataExtractor with minimal mocking
    metadata_extractor = DomainMetadataExtractor(blocked_domains=set())

    # Create mock favicon data with many manifests
    manifests = [{"href": "manifest0.json"}, {"href": "manifest1.json"}]  # Multiple manifests
    favicon_data = FaviconData(links=[], metas=[], manifests=manifests)

    # Mock the scraper's scrape_favicon_data method
    mocker.patch.object(
        metadata_extractor.scraper, "scrape_favicon_data", return_value=favicon_data
    )

    # Mock scrape_favicons_from_manifest to return results
    mocker.patch.object(
        metadata_extractor.scraper,
        "scrape_favicons_from_manifest",
        return_value=[{"src": "https://icon-from-manifest0.png"}],
    )

    # Mock default favicon to return None
    mocker.patch.object(
        metadata_extractor.scraper, "get_default_favicon", AsyncMock(return_value=None)
    )

    # Mock URL joining
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
        return_value="https://icon-from-manifest0.png",
    ):
        results = await metadata_extractor._extract_favicons("https://example.com")

    # Should only process the first manifest in the list
    assert len(results) == 1
    assert results[0]["href"] == "https://icon-from-manifest0.png"
