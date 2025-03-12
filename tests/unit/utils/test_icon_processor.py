"""Unit tests for the IconProcessor utility."""

import hashlib
from unittest.mock import MagicMock, patch, AsyncMock
from urllib.parse import urljoin

import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.suggest.adm.backends.remotesettings import (
    RemoteSettingsBackend,
    KintoSuggestion,
)
from merino.utils.gcs.models import Image
from merino.utils.icon_processor import IconProcessor


@pytest.fixture
def icon_processor(mocker):
    """Create an IconProcessor instance for testing."""
    # Mock the GcsUploader to avoid connecting to Google Cloud
    mocker.patch("merino.utils.gcs.gcs_uploader.Client")

    mocker.patch.object(settings, "_wrapped", settings._wrapped)

    # Create a mock HTTP client for testing
    mock_http_client = AsyncMock()

    processor = IconProcessor(
        gcs_project=settings.image_gcs.gcs_project,
        gcs_bucket=settings.image_gcs.gcs_bucket,
        cdn_hostname=settings.image_gcs.cdn_hostname,
        http_client=mock_http_client,
    )

    return processor


@pytest.fixture
def mock_image():
    """Create a mock image for testing."""
    content = b"test_image_content"
    return Image(
        content=content,
        content_type="image/png",
    )


def test_init(mocker):
    """Test that the IconProcessor is properly initialized."""
    # Mock the GcsUploader to avoid connecting to Google Cloud
    mocker.patch("merino.utils.gcs.gcs_uploader.Client")

    # Create a mock HTTP client
    mock_client = AsyncMock()

    processor = IconProcessor(
        gcs_project=settings.image_gcs.gcs_project,
        gcs_bucket=settings.image_gcs.gcs_bucket,
        cdn_hostname=settings.image_gcs.cdn_hostname,
        http_client=mock_client,
    )

    assert processor.uploader is not None
    assert processor.content_hash_cache == {}
    assert processor.uploader.cdn_hostname == settings.image_gcs.cdn_hostname
    assert processor.http_client is mock_client


@pytest.mark.asyncio
async def test_process_icon_url_empty_url(icon_processor):
    """Test that an empty URL returns the original URL"""
    assert await icon_processor.process_icon_url("original.png") == "original.png"


@pytest.mark.asyncio
async def test_process_icon_url_already_cdn(icon_processor):
    """Test that URLs from our CDN are not processed."""
    cdn_url = f"https://{icon_processor.uploader.cdn_hostname}/some/path.png"
    result = await icon_processor.process_icon_url(cdn_url)
    assert result == cdn_url


@pytest.mark.asyncio
async def test_download_favicon_success(icon_processor):
    """Test successful favicon download."""
    url = "https://example.com/favicon.ico"

    # Create mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"image_content"
    mock_response.headers = {"Content-Type": "image/png"}
    mock_response.raise_for_status = MagicMock()

    # Configure the mock client (already created in the fixture)
    icon_processor.http_client.get.return_value = mock_response

    # Call the method
    result = await icon_processor._download_favicon(url)

    # Verify the result
    assert result is not None
    assert result.content == b"image_content"
    assert result.content_type == "image/png"

    # Verify client was called with correct parameters
    icon_processor.http_client.get.assert_called_once_with(url, headers={"User-Agent": "Merino"})


@pytest.mark.asyncio
async def test_download_favicon_failure(icon_processor):
    """Test favicon download failure."""
    url = "https://example.com/favicon.ico"

    # Create mock response with error status
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status = MagicMock(side_effect=Exception("404 Not Found"))

    # Configure the mock client
    icon_processor.http_client.get.return_value = mock_response

    # Call the method
    result = await icon_processor._download_favicon(url)

    # Should return None on failure
    assert result is None

    # Verify client was called
    icon_processor.http_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_download_favicon_exception(icon_processor):
    """Test favicon download exception handling."""
    url = "https://example.com/favicon.ico"

    # Configure mock client to raise an exception
    icon_processor.http_client.get.side_effect = Exception("Connection error")

    # Call the method
    result = await icon_processor._download_favicon(url)

    # Should return None on exception
    assert result is None

    # Verify client was called
    icon_processor.http_client.get.assert_called_once()


def test_is_valid_image(icon_processor, mock_image):
    """Test image validation."""
    # Test valid image
    assert icon_processor._is_valid_image(mock_image) is True

    # Test invalid content type
    invalid_type = Image(content=b"test", content_type="text/plain")
    assert icon_processor._is_valid_image(invalid_type) is False

    # Test too small image
    small_image = Image(content=b"test", content_type="image/png")
    assert icon_processor._is_valid_image(small_image) is False

    # Test too large image
    max_size = getattr(settings.icon, "max_size", 1024 * 1024)
    large_content = b"x" * (max_size + 1)
    large_image = Image(content=large_content, content_type="image/png")
    assert icon_processor._is_valid_image(large_image) is False


def test_get_destination_path(icon_processor, mock_image, mocker):
    """Test destination path generation."""
    # Mock settings to ensure consistent test behavior
    mock_settings = mocker.patch("merino.utils.icon_processor.settings")
    mock_settings.icon.favicons_root = "favicons"

    # Calculate expected content hash
    content_hex = hashlib.sha256(mock_image.content).hexdigest()
    content_len = str(len(mock_image.content))

    expected_path = f"favicons/{content_hex}_{content_len}.png"

    # Test with PNG image
    assert icon_processor._get_destination_path(mock_image, content_hex) == expected_path

    # Test with JPEG image
    jpeg_image = Image(content=mock_image.content, content_type="image/jpeg")
    expected_path = f"favicons/{content_hex}_{content_len}.jpeg"
    assert icon_processor._get_destination_path(jpeg_image, content_hex) == expected_path

    # Test with JPG image
    jpg_image = Image(content=mock_image.content, content_type="image/jpg")
    expected_path = f"favicons/{content_hex}_{content_len}.jpeg"
    assert icon_processor._get_destination_path(jpg_image, content_hex) == expected_path

    # Test with SVG image
    svg_image = Image(content=mock_image.content, content_type="image/svg+xml")
    expected_path = f"favicons/{content_hex}_{content_len}.svg"
    assert icon_processor._get_destination_path(svg_image, content_hex) == expected_path

    # Test with ICO image
    ico_image = Image(content=mock_image.content, content_type="image/x-icon")
    expected_path = f"favicons/{content_hex}_{content_len}.ico"
    assert icon_processor._get_destination_path(ico_image, content_hex) == expected_path

    # Test with WEBP image
    webp_image = Image(content=mock_image.content, content_type="image/webp")
    expected_path = f"favicons/{content_hex}_{content_len}.webp"
    assert icon_processor._get_destination_path(webp_image, content_hex) == expected_path

    # Test with GIF image
    gif_image = Image(content=mock_image.content, content_type="image/gif")
    expected_path = f"favicons/{content_hex}_{content_len}.gif"
    assert icon_processor._get_destination_path(gif_image, content_hex) == expected_path

    # Test with BMP image
    bmp_image = Image(content=mock_image.content, content_type="image/bmp")
    expected_path = f"favicons/{content_hex}_{content_len}.bmp"
    assert icon_processor._get_destination_path(bmp_image, content_hex) == expected_path

    # Test with TIFF image
    tiff_image = Image(content=mock_image.content, content_type="image/tiff")
    expected_path = f"favicons/{content_hex}_{content_len}.tiff"
    assert icon_processor._get_destination_path(tiff_image, content_hex) == expected_path


@pytest.mark.asyncio
async def test_process_icon_url_integration(icon_processor, mock_image, mocker: MockerFixture):
    """Test the full process_icon_url workflow."""
    url = "https://example.com/favicon.ico"

    # Mock the internal methods
    mocker.patch.object(icon_processor, "_download_favicon", return_value=mock_image)
    mocker.patch.object(icon_processor, "_is_valid_image", return_value=True)
    mocker.patch.object(
        icon_processor.uploader,
        "upload_image",
        return_value="https://cdn.test.mozilla.net/favicons/test_hash_17.png",
    )

    # Process the URL
    result = await icon_processor.process_icon_url(url)

    # Verify the result
    assert result == "https://cdn.test.mozilla.net/favicons/test_hash_17.png"

    # Get content hash
    content_hash = hashlib.sha256(mock_image.content).hexdigest()

    # Verify it was added to the content hash cache
    assert content_hash in icon_processor.content_hash_cache
    assert (
        icon_processor.content_hash_cache[content_hash]
        == "https://cdn.test.mozilla.net/favicons/test_hash_17.png"
    )


@pytest.mark.asyncio
async def test_process_icon_url_content_hash_cache(
    icon_processor, mock_image, mocker: MockerFixture
):
    """Test the content hash cache is used."""
    url = "https://example.com/favicon.ico"
    content_hash = hashlib.sha256(mock_image.content).hexdigest()

    # Add to content hash cache
    icon_processor.content_hash_cache[content_hash] = (
        "https://cdn.test.mozilla.net/favicons/cached.png"
    )

    # Mock the internal methods
    mocker.patch.object(icon_processor, "_download_favicon", return_value=mock_image)
    mocker.patch.object(icon_processor, "_is_valid_image", return_value=True)

    # Create a spy on the upload_image method
    upload_spy = mocker.spy(icon_processor.uploader, "upload_image")

    # Process the URL
    result = await icon_processor.process_icon_url(url)

    # Verify the result is from the content hash cache
    assert result == "https://cdn.test.mozilla.net/favicons/cached.png"

    # Verify the uploader was not called
    assert upload_spy.call_count == 0


@pytest.mark.asyncio
async def test_process_icon_url_exception(icon_processor, mocker: MockerFixture):
    """Test exception handling in process_icon_url."""
    url = "https://example.com/favicon.ico"

    # Mock to raise an exception
    mocker.patch.object(icon_processor, "_download_favicon", side_effect=Exception("Test error"))

    # Process the URL
    result = await icon_processor.process_icon_url(url)

    # Should return the original URL
    assert result == url


@pytest.mark.asyncio
async def test_process_icon_url_download_failure(icon_processor, mocker: MockerFixture):
    """Test handling of favicon download failure."""
    url = "https://example.com/favicon.ico"

    # Mock download to return None (download failure)
    mocker.patch.object(icon_processor, "_download_favicon", return_value=None)

    # Process the URL
    result = await icon_processor.process_icon_url(url)

    # Should return the original URL
    assert result == url


@pytest.mark.asyncio
async def test_process_icon_url_invalid_image(icon_processor, mock_image, mocker: MockerFixture):
    """Test handling of invalid image in process_icon_url."""
    url = "https://example.com/favicon.ico"

    # Mock download to return a valid image
    mocker.patch.object(icon_processor, "_download_favicon", return_value=mock_image)

    # But mock _is_valid_image to return False
    mocker.patch.object(icon_processor, "_is_valid_image", return_value=False)

    # Process the URL
    result = await icon_processor.process_icon_url(url)

    # Should return the original URL
    assert result == url


def test_detect_extension_from_content_type(icon_processor, mock_image):
    """Test detecting extension from content type."""
    # Test with custom image type
    custom_image = Image(content=mock_image.content, content_type="image/custom")
    content_hash = hashlib.sha256(custom_image.content).hexdigest()
    dest_path = icon_processor._get_destination_path(custom_image, content_hash)
    # Should extract extension from content type
    assert dest_path.endswith(".custom")


@patch("merino.utils.gcs.models.Image.open")
def test_detect_extension_from_unknown_content_type(mock_open, icon_processor, mock_image, mocker):
    """Test detecting extension for unknown content type."""
    # Non-image content type
    unknown_image = Image(content=mock_image.content, content_type="unknown/type")
    content_hash = hashlib.sha256(unknown_image.content).hexdigest()

    # Mock PIL Image return with format attribute
    mock_pil_image = mocker.MagicMock()
    mock_pil_image.format = "JPEG"
    mock_open.return_value.__enter__.return_value = mock_pil_image

    # Should attempt to detect from content and update content_type
    dest_path = icon_processor._get_destination_path(unknown_image, content_hash)
    assert dest_path.endswith(".jpeg")
    assert unknown_image.content_type == "image/jpeg"


@patch("merino.utils.gcs.models.Image.open")
def test_detect_different_image_formats(mock_open, icon_processor, mock_image, mocker):
    """Test detecting different image formats and updating content types."""
    formats_to_test = [
        ("PNG", "image/png"),
        ("SVG", "image/svg"),
        ("WEBP", "image/webp"),
        ("GIF", "image/gif"),
        ("BMP", "image/bmp"),
        ("TIFF", "image/tiff"),
        ("ICO", "image/x-icon"),
    ]

    for img_format, expected_content_type in formats_to_test:
        # Non-image content type
        unknown_image = Image(content=mock_image.content, content_type="unknown/type")
        content_hash = hashlib.sha256(unknown_image.content).hexdigest()

        # Mock PIL Image return with format attribute
        mock_pil_image = mocker.MagicMock()
        mock_pil_image.format = img_format
        mock_open.return_value.__enter__.return_value = mock_pil_image

        # Should attempt to detect from content and update content_type
        dest_path = icon_processor._get_destination_path(unknown_image, content_hash)
        assert dest_path.endswith(f".{img_format.lower()}")
        assert unknown_image.content_type == expected_content_type


@patch("merino.utils.gcs.models.Image.open")
def test_detect_extension_from_unknown_content_type_fail(mock_open, icon_processor, mock_image):
    """Test handling of failure to detect from unknown content type."""
    # Non-image content type
    unknown_image = Image(content=mock_image.content, content_type="unknown/type")
    content_hash = hashlib.sha256(unknown_image.content).hexdigest()

    # Set up mock to raise an exception
    mock_open.side_effect = Exception("Cannot determine image format")

    # Should default to png extension
    dest_path = icon_processor._get_destination_path(unknown_image, content_hash)
    assert dest_path.endswith(".png")
    assert unknown_image.content_type == "image/png"


def test_custom_favicons_root(icon_processor, mock_image, mocker):
    """Test using custom favicons_root from settings."""
    # Mock settings to simulate custom favicons_root
    mock_settings = mocker.patch("merino.utils.icon_processor.settings")
    mock_settings.icon.favicons_root = "custom_icons"

    # Calculate expected hash and length
    content_hex = hashlib.sha256(mock_image.content).hexdigest()
    content_len = str(len(mock_image.content))

    # Get destination path
    dest_path = icon_processor._get_destination_path(mock_image, content_hex)

    # Should use custom root
    assert dest_path == f"custom_icons/{content_hex}_{content_len}.png"


@pytest.mark.asyncio
async def test_fetch_with_icon_processing_errors():
    """Test handling of exceptions during icon processing."""
    # Mock data
    mock_records = [
        {"id": "icon-123", "attachment": {"location": "/path/to/icon1.png"}},
        {"id": "icon-456", "attachment": {"location": "/path/to/icon2.png"}},
        {"id": "icon-789", "attachment": {"location": "/path/to/icon3.png"}},
    ]
    mock_suggestions = [
        KintoSuggestion(
            id=id,
            advertiser="Example.org",
            iab_category="5 - Education",
            icon=icon_id,
            title="Test Suggestion",
            url="https://example.org/test",
        )
        for id, icon_id in enumerate(["123", "456", "789"])
    ]
    attachment_host = "https://example.com"

    # Create instance with mock icon processor
    icon_processor_mock = MagicMock(spec=IconProcessor)
    backend = RemoteSettingsBackend("server", "collection", "bucket", icon_processor_mock)

    # Mock the methods directly on the instance
    backend.get_records = AsyncMock(return_value=[])
    backend.get_attachment_host = AsyncMock(return_value=attachment_host)
    backend.get_suggestions = AsyncMock(return_value=mock_suggestions)
    backend.filter_records = MagicMock(return_value=mock_records)

    # Mock icon processor's process_icon_url method with different behaviors
    async def mock_process_side_effect(url):
        if "icon1" in url:
            return "https://processed.example.com/icon1.png"
        elif "icon2" in url:
            raise ValueError("Processing failed")
        elif "icon3" in url:
            raise Exception("Connection error")

    backend.icon_processor.process_icon_url = AsyncMock(side_effect=mock_process_side_effect)

    # Call the method we're testing
    result = await backend.fetch()

    # Assertions
    assert "123" in result.icons
    assert "456" in result.icons
    assert "789" in result.icons

    # Check successful processing
    assert result.icons["123"] == "https://processed.example.com/icon1.png"

    # Check fallback URLs for failed processing
    expected_fallback_url = urljoin(base=attachment_host, url="/path/to/icon2.png")
    assert result.icons["456"] == expected_fallback_url

    expected_fallback_url = urljoin(base=attachment_host, url="/path/to/icon3.png")
    assert result.icons["789"] == expected_fallback_url
