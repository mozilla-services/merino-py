# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Additional tests for the domain metadata extractor to improve coverage."""

import io
import pytest
from PIL import Image as PILImage
from unittest.mock import AsyncMock

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
)
from merino.utils.gcs.models import Image


@pytest.mark.asyncio
async def test_is_problematic_favicon_url():
    """Test the _is_problematic_favicon_url method with various URLs."""
    extractor = DomainMetadataExtractor(set())

    # Test data URLs (should be problematic)
    assert extractor._is_problematic_favicon_url("data:image/png;base64,ABC123") is True

    # Test manifest JSON base64 marker URLs (should be problematic)
    assert (
        extractor._is_problematic_favicon_url("something/application/manifest+json;base64,xyz")
        is True
    )

    # Test normal URLs (should not be problematic)
    assert extractor._is_problematic_favicon_url("https://example.com/favicon.ico") is False
    assert extractor._is_problematic_favicon_url("/favicon.ico") is False


@pytest.mark.asyncio
async def test_fix_url():
    """Test the _fix_url method with various URLs."""
    extractor = DomainMetadataExtractor(set())

    # Empty URL or single slash
    assert extractor._fix_url("") == ""
    assert extractor._fix_url("/") == ""

    # Protocol-relative URLs
    assert extractor._fix_url("//example.com/favicon.ico") == "https://example.com/favicon.ico"

    # URLs without protocol
    assert extractor._fix_url("example.com/favicon.ico") == "https://example.com/favicon.ico"

    # Absolute paths with base URL context
    extractor._current_base_url = "https://example.com"
    assert extractor._fix_url("/favicon.ico") == "https://example.com/favicon.ico"

    # Absolute paths without base URL context
    delattr(extractor, "_current_base_url")
    assert extractor._fix_url("/favicon.ico") == ""

    # URLs that already have a protocol
    assert (
        extractor._fix_url("https://example.com/favicon.ico") == "https://example.com/favicon.ico"
    )


@pytest.mark.asyncio
async def test_get_favicon_smallest_dimension():
    """Test the _get_favicon_smallest_dimension method."""
    extractor = DomainMetadataExtractor(set())

    # Create a test image that will return specific dimensions
    img_data = io.BytesIO()
    test_image = PILImage.new("RGB", (100, 50))
    test_image.save(img_data, format="PNG")
    img_data.seek(0)

    # Create an Image object with methods that mock PIL's behavior
    test_image_obj = Image(content=img_data.getvalue(), content_type="image/png")

    # Test the smallest dimension (should be 50)
    assert extractor._get_favicon_smallest_dimension(test_image_obj) == 50

    # Test with a square image
    img_data = io.BytesIO()
    test_image = PILImage.new("RGB", (75, 75))
    test_image.save(img_data, format="PNG")
    img_data.seek(0)
    test_image_obj = Image(content=img_data.getvalue(), content_type="image/png")

    # Both dimensions are the same, so it should return 75
    assert extractor._get_favicon_smallest_dimension(test_image_obj) == 75


@pytest.mark.asyncio
async def test_extract_favicons_with_default_favicon_url(mocker):
    """Test _extract_favicons method when a default favicon URL is found."""
    extractor = DomainMetadataExtractor(set())

    # Mock favicon data with no links, metas, or manifests
    favicon_data = FaviconData(links=[], metas=[], manifests=[])
    mocker.patch.object(extractor.scraper, "scrape_favicon_data", return_value=favicon_data)

    # Mock the default favicon URL
    default_favicon_url = "https://example.com/favicon.ico"
    mocker.patch.object(
        extractor.scraper, "get_default_favicon", AsyncMock(return_value=default_favicon_url)
    )

    # Call the method
    results = await extractor._extract_favicons("https://example.com")

    # Should include the default favicon
    assert len(results) == 1
    assert results[0]["href"] == default_favicon_url


@pytest.mark.asyncio
async def test_extract_favicons_error_handling(mocker):
    """Test error handling in _extract_favicons method."""
    extractor = DomainMetadataExtractor(set())

    # Make scrape_favicon_data raise an exception
    mocker.patch.object(
        extractor.scraper, "scrape_favicon_data", side_effect=Exception("Test exception")
    )

    # Call the method - it should handle the exception and return an empty list
    results = await extractor._extract_favicons("https://example.com")

    # Should return an empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_upload_best_favicon_with_svg(mocker, mock_domain_metadata_uploader):
    """Test _upload_best_favicon method with an SVG favicon."""
    extractor = DomainMetadataExtractor(set())

    # Create test favicons list with an SVG
    favicons = [{"href": "https://example.com/icon.svg", "rel": "icon"}]

    # Mock download_multiple_favicons to return an SVG image
    svg_image = Image(content=b"<svg></svg>", content_type="image/svg+xml")
    mocker.patch.object(
        extractor.favicon_downloader,
        "download_multiple_favicons",
        AsyncMock(return_value=[svg_image]),
    )

    # Mock uploader methods
    mock_domain_metadata_uploader.destination_favicon_name.return_value = "favicons/svg_icon.svg"
    mock_domain_metadata_uploader.upload_image.return_value = (
        "https://cdn.example.com/favicons/svg_icon.svg"
    )

    # Call the method
    result = await extractor._upload_best_favicon(favicons, 16, mock_domain_metadata_uploader)

    # Should return the uploaded SVG URL
    assert result == "https://cdn.example.com/favicons/svg_icon.svg"

    # Verify uploader was called correctly
    mock_domain_metadata_uploader.upload_image.assert_called_once()


@pytest.mark.asyncio
async def test_upload_best_favicon_svg_upload_error(mocker, mock_domain_metadata_uploader):
    """Test _upload_best_favicon method with an SVG favicon that fails to upload."""
    extractor = DomainMetadataExtractor(set())

    # Create test favicons list with an SVG
    favicons = [{"href": "https://example.com/icon.svg", "rel": "icon"}]

    # Mock download_multiple_favicons to return an SVG image
    svg_image = Image(content=b"<svg></svg>", content_type="image/svg+xml")
    mocker.patch.object(
        extractor.favicon_downloader,
        "download_multiple_favicons",
        AsyncMock(return_value=[svg_image]),
    )

    # Mock uploader to throw an exception
    mock_domain_metadata_uploader.upload_image.side_effect = Exception("Upload failed")

    # Call the method
    result = await extractor._upload_best_favicon(favicons, 16, mock_domain_metadata_uploader)

    # Should fall back to the original URL
    assert result == "https://example.com/icon.svg"


@pytest.mark.asyncio
async def test_upload_best_favicon_bitmap_upload_error(mocker, mock_domain_metadata_uploader):
    """Test _upload_best_favicon method with a bitmap favicon that fails to upload."""
    extractor = DomainMetadataExtractor(set())

    # Create test favicons list with a PNG
    favicons = [{"href": "https://example.com/icon.png", "rel": "icon"}]

    # Create a mock image
    img_data = io.BytesIO()
    test_image = PILImage.new("RGB", (32, 32))
    test_image.save(img_data, format="PNG")
    img_data.seek(0)

    # Mock download_multiple_favicons to return a PNG image
    png_image = Image(content=img_data.getvalue(), content_type="image/png")
    mocker.patch.object(
        extractor.favicon_downloader,
        "download_multiple_favicons",
        AsyncMock(return_value=[png_image]),
    )

    # Mock uploader to throw an exception
    mock_domain_metadata_uploader.upload_image.side_effect = Exception("Upload failed")

    # Mock _get_favicon_smallest_dimension
    mocker.patch.object(extractor, "_get_favicon_smallest_dimension", return_value=32)

    # Call the method
    result = await extractor._upload_best_favicon(favicons, 16, mock_domain_metadata_uploader)

    # Should fall back to the original URL
    assert result == "https://example.com/icon.png"


@pytest.mark.asyncio
async def test_process_favicon(mocker, mock_domain_metadata_uploader):
    """Test the _process_favicon method."""
    extractor = DomainMetadataExtractor(set())

    # Mock _extract_favicons
    favicons = [{"href": "https://example.com/favicon.ico"}]
    mocker.patch.object(extractor, "_extract_favicons", AsyncMock(return_value=favicons))

    # Mock _upload_best_favicon
    expected_url = "https://cdn.example.com/favicons/uploaded.ico"
    mocker.patch.object(extractor, "_upload_best_favicon", AsyncMock(return_value=expected_url))

    # Call the method
    result = await extractor._process_favicon(
        "https://example.com", 16, mock_domain_metadata_uploader
    )

    # Should return the result of _upload_best_favicon
    assert result == expected_url

    # Verify _extract_favicons was called with the correct parameters
    extractor._extract_favicons.assert_called_once_with("https://example.com", max_icons=5)

    # Verify _upload_best_favicon was called with the correct parameters
    extractor._upload_best_favicon.assert_called_once_with(
        favicons, 16, mock_domain_metadata_uploader
    )
