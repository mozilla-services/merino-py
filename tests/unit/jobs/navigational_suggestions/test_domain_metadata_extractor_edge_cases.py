# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_metadata_extractor.py edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from merino.utils.gcs.models import Image
from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
)


@pytest.fixture
def mock_domain_metadata_uploader():
    """Create a mock domain metadata uploader."""
    mock_uploader = MagicMock()
    mock_uploader.upload_favicon.return_value = "https://cdn.example.com/test-favicon.ico"
    mock_uploader.destination_favicon_name.return_value = "favicons/test.icon"
    mock_uploader.upload_image.return_value = "https://cdn.example.com/test-favicon.ico"
    return mock_uploader


@pytest.fixture
def mock_scraper():
    """Create a mock scraper."""
    mock_scraper = MagicMock(spec=Scraper)
    mock_scraper.open.return_value = "https://example.com"
    mock_scraper.scrape_title.return_value = "Example Website"
    mock_scraper.scrape_favicon_data.return_value = FaviconData(
        links=[{"rel": "icon", "href": "favicon.ico"}], metas=[], manifests=[]
    )
    mock_scraper.get_default_favicon = AsyncMock(return_value="https://example.com/favicon.ico")
    mock_scraper.scrape_favicons_from_manifest = AsyncMock(return_value=[])
    return mock_scraper


@pytest.fixture
def extractor_with_mock_scraper(mock_scraper):
    """Create an extractor with a mock scraper."""
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper",
        return_value=mock_scraper,
    ):
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.scraper = mock_scraper
        return extractor, mock_scraper


def test_process_domains_error_handling(
    extractor_with_mock_scraper, mock_domain_metadata_uploader
):
    """Test error handling in _process_domains method."""
    extractor, mock_scraper = extractor_with_mock_scraper

    # Create a mock for errors during processing
    mock_process_domain = AsyncMock(
        side_effect=[
            {
                "domain": None,
                "url": None,
                "title": None,
                "icon": None,
            },  # Empty dict for first domain
            {
                "domain": "success.com",
                "url": "https://success.com",
                "title": "Success",
                "icon": "icon",
            },
            # Success for second
        ]
    )
    extractor._process_single_domain = mock_process_domain

    # Create test data
    domain_data = [
        {"domain": "error.com", "suffix": "com", "rank": 1, "categories": ["web"]},
        {"domain": "success.com", "suffix": "com", "rank": 2, "categories": ["shopping"]},
    ]

    # Process domains
    result = extractor.process_domain_metadata(domain_data, 48, mock_domain_metadata_uploader)

    # Verify error handling worked correctly - should include both domains
    assert len(result) == 2
    assert result[0] == {"domain": None, "url": None, "title": None, "icon": None}
    assert result[1] == {
        "domain": "success.com",
        "url": "https://success.com",
        "title": "Success",
        "icon": "icon",
    }


@pytest.mark.asyncio
async def test_extract_favicons_with_empty_href(extractor_with_mock_scraper):
    """Test _extract_favicons method when link has empty href."""
    extractor, mock_scraper = extractor_with_mock_scraper

    # Mock favicon data with empty href
    empty_href_data = FaviconData(links=[{"rel": "icon", "href": ""}], metas=[], manifests=[])
    mock_scraper.scrape_favicon_data.return_value = empty_href_data
    mock_scraper.get_default_favicon.return_value = None

    # Create a mock for urljoin that converts empty href to base URL
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
        return_value="https://example.com",
    ):
        # Call the method
        result = await extractor._extract_favicons("https://example.com")

    # Should have one favicon with the base URL
    assert len(result) == 1
    assert result[0]["href"] == "https://example.com"


@pytest.mark.asyncio
async def test_upload_best_favicon_with_svg(
    extractor_with_mock_scraper, mock_domain_metadata_uploader
):
    """Test _upload_best_favicon method with an SVG favicon."""
    extractor, _ = extractor_with_mock_scraper

    # Create test favicons list with an SVG
    favicons = [{"href": "https://example.com/icon.svg", "rel": "icon"}]

    # Mock download_multiple_favicons to return an SVG image
    svg_image = Image(content=b"<svg></svg>", content_type="image/svg+xml")
    extractor.favicon_downloader = AsyncMock()
    extractor.favicon_downloader.download_multiple_favicons.return_value = [svg_image]

    # Mock uploader methods
    mock_domain_metadata_uploader.destination_favicon_name.return_value = "favicons/svg_icon.svg"
    mock_domain_metadata_uploader.upload_image.return_value = (
        "https://cdn.example.com/favicons/svg_icon.svg"
    )

    # Fix URL
    extractor._fix_url = lambda url: url["href"] if isinstance(url, dict) else url
    extractor._is_problematic_favicon_url = lambda url: False

    # Call the method
    result = await extractor._upload_best_favicon(favicons, 16, mock_domain_metadata_uploader)

    # Should return the uploaded SVG URL
    assert result == "https://cdn.example.com/favicons/svg_icon.svg"

    # Verify uploader was called correctly
    mock_domain_metadata_uploader.upload_image.assert_called_once()


@pytest.mark.asyncio
async def test_upload_best_favicon_batching(
    extractor_with_mock_scraper, mock_domain_metadata_uploader
):
    """Test batched processing in _upload_best_favicon method."""
    extractor, _ = extractor_with_mock_scraper

    # Create a list of favicon dictionaries
    favicon_urls = [{"href": f"https://example{i}.com/favicon.ico"} for i in range(20)]

    # Create an image with SVG content type to trigger the SVG upload path
    svg_image = Image(
        content=b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"></svg>',
        content_type="image/svg+xml",
    )

    # Mock the AsyncFaviconDownloader
    mock_downloader = AsyncMock()
    mock_downloader.download_multiple_favicons.return_value = [svg_image] + [
        Image(content=b"test", content_type="image/png") for _ in range(19)
    ]
    extractor.favicon_downloader = mock_downloader

    # Mock the _fix_url method to return valid URLs
    extractor._fix_url = lambda url: url.get("href", "") if isinstance(url, dict) else url
    extractor._is_problematic_favicon_url = lambda url: False

    # Run the method with the favicons list
    with patch.object(extractor, "_get_favicon_smallest_dimension", return_value=32):
        result = await extractor._upload_best_favicon(
            favicon_urls, 32, mock_domain_metadata_uploader
        )

    # Verify we got a result
    assert result == "https://cdn.example.com/test-favicon.ico"

    # Verify downloader was called
    assert mock_downloader.download_multiple_favicons.called


@pytest.mark.asyncio
async def test_extract_favicons_with_problematic_urls(extractor_with_mock_scraper):
    """Test _extract_favicons method with problematic URLs."""
    extractor, mock_scraper = extractor_with_mock_scraper

    # Mock favicon data with problematic URLs
    problem_data = FaviconData(
        links=[
            {"rel": "icon", "href": "data:image/png;base64,ABC123"},  # Data URL
            {
                "rel": "icon",
                "href": "something/application/manifest+json;base64,xyz",
            },  # Base64 manifest
            {"rel": "icon", "href": "valid.ico"},  # Valid URL
        ],
        metas=[],
        manifests=[],
    )
    mock_scraper.scrape_favicon_data.return_value = problem_data
    mock_scraper.get_default_favicon.return_value = None

    # Mock urljoin
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
        return_value="https://example.com/valid.ico",
    ):
        # Call the method
        result = await extractor._extract_favicons("https://example.com")

    # Should only include the valid URL
    assert len(result) == 1
    assert "valid.ico" in str(result[0])


@pytest.mark.asyncio
async def test_fix_url_with_empty_url(extractor_with_mock_scraper):
    """Test _fix_url method with empty URLs."""
    extractor, _ = extractor_with_mock_scraper

    # Test empty string
    assert extractor._fix_url("") == ""

    # Test single slash
    assert extractor._fix_url("/") == ""


@pytest.mark.asyncio
async def test_fix_url_with_absolute_path(extractor_with_mock_scraper):
    """Test _fix_url method with absolute paths."""
    extractor, _ = extractor_with_mock_scraper

    # Test absolute path without base URL
    assert extractor._fix_url("/favicon.ico") == ""

    # Test absolute path with base URL
    extractor._current_base_url = "https://example.com"
    assert extractor._fix_url("/favicon.ico") == "https://example.com/favicon.ico"


@pytest.mark.asyncio
async def test_process_single_domain_with_exception(
    extractor_with_mock_scraper, mock_domain_metadata_uploader
):
    """Test _process_single_domain method with an exception."""
    extractor, _ = extractor_with_mock_scraper

    # Make _get_base_url raise an exception
    extractor._get_base_url = MagicMock(side_effect=Exception("Test exception"))

    # Call the method
    domain_data = {"domain": "example.com", "suffix": "com"}
    result = await extractor._process_single_domain(domain_data, 16, mock_domain_metadata_uploader)

    # Should return default values
    assert result == {"url": None, "title": None, "icon": None, "domain": None}


@pytest.mark.asyncio
async def test_process_domains_with_exceptions(mocker, mock_domain_metadata_uploader):
    """Test that _process_domains properly handles exceptions in the processing"""
    # Create the extractor
    extractor = DomainMetadataExtractor(blocked_domains=set())

    # Mock _process_single_domain to raise an exception for example2.com
    async def mock_process_domain(domain_data, min_width, uploader):
        if domain_data["domain"] == "example2.com":
            raise Exception("Test exception")
        return {
            "url": f"https://www.{domain_data['domain']}",
            "title": domain_data["domain"].split(".")[0],
            "icon": f"https://{domain_data['domain']}/favicon.ico",
            "domain": domain_data["domain"].split(".")[0],
        }

    mocker.patch.object(extractor, "_process_single_domain", side_effect=mock_process_domain)

    # Create test data
    domain_data = [
        {"domain": "example1.com", "suffix": "com"},
        {"domain": "example2.com", "suffix": "com"},  # This one will throw an exception
        {"domain": "example3.com", "suffix": "com"},
    ]

    # Process domains
    result = await extractor._process_domains(domain_data, 32, mock_domain_metadata_uploader)

    # Verify that we get results for the two domains that didn't throw exceptions
    assert len(result) == 2
    assert result[0]["domain"] == "example1"
    assert result[1]["domain"] == "example3"

    # Verify that each domain was processed (even the one with exception)
    assert extractor._process_single_domain.call_count == 3


@pytest.mark.asyncio
async def test_extract_title_with_invalid_titles(extractor_with_mock_scraper):
    """Test _extract_title method with various invalid titles."""
    extractor, mock_scraper = extractor_with_mock_scraper

    invalid_titles = [
        "Access denied",
        "Just a moment...",
        "Your request has been blocked",
        "404 Not Found",
        "   Error   Page  ",  # With extra whitespace
    ]

    for title in invalid_titles:
        mock_scraper.scrape_title.return_value = title
        result = extractor._extract_title()
        assert result is None, f"Title '{title}' should be rejected"

    # Test with valid title
    mock_scraper.scrape_title.return_value = "Valid Website Title"
    result = extractor._extract_title()
    assert result == "Valid Website Title"


@pytest.mark.asyncio
async def test_process_favicon_empty_favicons(
    extractor_with_mock_scraper, mock_domain_metadata_uploader
):
    """Test _process_favicon method with empty favicons list."""
    extractor, _ = extractor_with_mock_scraper

    # Mock _extract_favicons to return empty list
    with patch.object(extractor, "_extract_favicons", AsyncMock(return_value=[])):
        with patch.object(extractor, "_upload_best_favicon", AsyncMock(return_value="")):
            result = await extractor._process_favicon(
                "https://example.com", 16, mock_domain_metadata_uploader
            )

            # Should return empty string
            assert result == ""

            # _upload_best_favicon should be called with empty list
            extractor._upload_best_favicon.assert_called_once_with(
                [], 16, mock_domain_metadata_uploader
            )


@pytest.mark.asyncio
async def test_extract_favicons_with_manifest_chunk_processing(
    mocker, extractor_with_mock_scraper
):
    """Test that _extract_favicons correctly processes the first manifest"""
    extractor, mock_scraper = extractor_with_mock_scraper

    # Create mock favicon data with many manifests
    manifests = [{"href": "manifest0.json"}, {"href": "manifest1.json"}]  # Multiple manifests
    favicon_data = FaviconData(links=[], metas=[], manifests=manifests)
    mock_scraper.scrape_favicon_data.return_value = favicon_data

    # Create a specific mock for scrape_favicons_from_manifest
    scrape_manifests_mock = AsyncMock()
    scrape_manifests_mock.return_value = [{"src": "https://icon-from-manifest0.png"}]
    mock_scraper.scrape_favicons_from_manifest = scrape_manifests_mock

    # Mock default favicon to return None
    mock_scraper.get_default_favicon.return_value = None

    # Create a more specific urljoin mock that captures manifest URLs
    def urljoin_side_effect(base, url):
        if url == "manifest0.json":
            return "https://example.com/manifest0.json"
        return "https://icon-from-manifest0.png"

    # Mock URL joining
    with patch(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
        side_effect=urljoin_side_effect,
    ):
        results = await extractor._extract_favicons("https://example.com")

    # Should only process the first manifest in the list
    assert len(results) == 1
    assert results[0]["href"] == "https://icon-from-manifest0.png"

    # Verify manifest processing - the mock was called with the manifest URL
    scrape_manifests_mock.assert_called_once()
    call_arg = scrape_manifests_mock.call_args[0][0]
    assert "manifest0.json" in call_arg
    assert "manifest1.json" not in str(mock_scraper.scrape_favicons_from_manifest.call_args)
