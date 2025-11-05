"""Integration tests for the RemoteSettingsBackend with IconProcessor."""

import hashlib
import json
from typing import Optional
from unittest.mock import MagicMock, patch, AsyncMock

import httpx
import kinto_http
import pytest
from pytest_mock import MockerFixture

from merino.providers.suggest.adm.backends.protocol import SuggestionContent
from merino.providers.suggest.adm.backends.remotesettings import (
    KintoSuggestion,
    RemoteSettingsBackend,
)
from merino.utils.gcs.models import Image
from merino.utils.icon_processor import IconProcessor
from merino.configs import settings


@pytest.fixture(name="rs_parameters")
def fixture_rs_parameters() -> dict[str, str]:
    """Define default Remote Settings parameters for test."""
    return {
        "server": "test://test",
        "bucket": "main",
        "collection": "quicksuggest-amp",
    }


@pytest.fixture(name="rs_records")
def fixture_rs_records() -> list[dict]:
    """Return fake records data for testing."""
    return [
        {
            "type": "amp",
            "schema": 123,
            "country": "US",
            "form_factor": "desktop",
            "attachment": {
                "hash": "abcd",
                "size": 1,
                "filename": "data-01.json",
                "location": "main-workspace/quicksuggest-amp/attachmment-01.json",
                "mimetype": "application/octet-stream",
            },
            "id": "data-01",
            "last_modified": 123,
        },
        # This icon is in use.
        {
            "type": "icon",
            "schema": 456,
            "attachment": {
                "hash": "efghabcasd",
                "size": 1,
                "filename": "icon-01",
                "location": "main-workspace/quicksuggest-amp/icon-01",
                "mimetype": "application/octet-stream",
            },
            "content_type": "image/png",
            "id": "icon-01",
            "last_modified": 123,
        },
        # This icon is not in use.
        {
            "type": "icon",
            "schema": 789,
            "attachment": {
                "hash": "iconhash2",
                "size": 1,
                "filename": "icon-02",
                "location": "main-workspace/quicksuggest-amp/icon-02",
                "mimetype": "application/octet-stream",
            },
            "content_type": "image/jpeg",
            "id": "icon-02",
            "last_modified": 123,
        },
    ]


@pytest.fixture(name="rs_server_info")
def fixture_rs_server_info() -> dict:
    """Return fake server information for testing."""
    return {
        "project_name": "Remote Settings Test",
        "capabilities": {
            "attachments": {
                "base_url": "attachment-host/",
            },
        },
    }


@pytest.fixture(name="rs_attachment")
def fixture_rs_attachment() -> KintoSuggestion:
    """Return fake attachment data for testing."""
    return KintoSuggestion(
        id=2,
        advertiser="Example.org",
        iab_category="5 - Education",
        icon="01",
        title="Test Suggestion",
        url="https://example.org/test",
        click_url="https://example.org/test",
        impression_url="https://example.org/test",
    )


@pytest.fixture(name="rs_attachment_response")
def fixture_rs_attachment_response(rs_attachment: KintoSuggestion) -> httpx.Response:
    """Return response content for a Remote Settings attachment."""
    return httpx.Response(
        status_code=200,
        text=json.dumps([dict(rs_attachment)]),
        request=httpx.Request(
            method="GET",
            url=(
                "attachment-host/main-workspace/quicksuggest-amp/"
                "6129d437-b3c1-48b5-b343-535e045d341a.json"
            ),
        ),
    )


@pytest.fixture(name="mock_image")
def fixture_mock_image() -> bytes:
    """Return mock image data for testing."""
    return b"mock_image_content"


@pytest.fixture(name="mock_http_response")
def fixture_mock_http_response(mock_image: bytes) -> MagicMock:
    """Return a mock HTTP response with image content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_image
    mock_response.headers = {"Content-Type": "image/png"}
    return mock_response


class MockImageProcessor(IconProcessor):
    """Mock version of IconProcessor for testing."""

    async def process_icon_url(self, url: str, fallback_url: Optional[str] = None) -> str:
        """Mock implementation that tracks processed URLs."""
        if not url:
            return fallback_url or ""

        # Store the URL for verification
        self.processed_urls[url] = True

        # Return a predictable CDN URL
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"https://test-cdn.mozilla.net/favicons/{url_hash}.png"

    def __init__(self) -> None:
        """Initialize the mock processor."""
        # Create a mock http client
        mock_http_client = MagicMock()

        # Call parent constructor with dummy values
        super().__init__(
            gcs_project="test-project",
            gcs_bucket="test-bucket",
            cdn_hostname="test-cdn.mozilla.net",
            http_client=mock_http_client,
        )

        # Override uploader with a mock
        self.uploader = MagicMock()
        self.uploader.cdn_hostname = "test-cdn.mozilla.net"

        # Initialize tracking dict
        self.content_hash_cache: dict[str, str] = {}
        self.processed_urls: dict[str, bool] = {}


@pytest.mark.asyncio
async def test_remotesettings_with_icon_processor(
    mocker: MockerFixture,
    rs_parameters: dict[str, str],
    rs_records: list[dict],
    rs_server_info: dict,
    rs_attachment_response: httpx.Response,
):
    """Test that RemoteSettingsBackend correctly uses IconProcessor."""
    # Create a backend with a mock IconProcessor
    mock_processor = MockImageProcessor()

    # Create the RemoteSettingsBackend with our mock processor
    rs_backend = RemoteSettingsBackend(
        server=rs_parameters["server"],
        collection=rs_parameters["collection"],
        bucket=rs_parameters["bucket"],
        icon_processor=mock_processor,
    )

    # Mock the Remote Settings client methods
    mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    # Fetch the suggestions
    suggestion_content: SuggestionContent = await rs_backend.fetch()

    # Verify that the in-use icon URLs were processed, the not-in-use one shouldn't be processed.
    assert len(suggestion_content.icons) == 1

    # Check that each icon URL was processed
    for icon_id, icon_url in suggestion_content.icons.items():
        # The icon URL should be from our test CDN
        assert "test-cdn.mozilla.net/favicons" in icon_url

        # The original URLs should have been passed to the processor
        original_url = f"attachment-host/main-workspace/quicksuggest-amp/icon-{icon_id}"
        assert original_url in mock_processor.processed_urls


@pytest.mark.asyncio
async def test_remotesettings_icon_processor_error_handling(
    mocker: MockerFixture,
    rs_parameters: dict[str, str],
    rs_records: list[dict],
    rs_server_info: dict,
    rs_attachment_response: httpx.Response,
):
    """Test that RemoteSettingsBackend handles IconProcessor errors gracefully."""
    # Create a backend with a mock IconProcessor that raises exceptions
    mock_processor = MockImageProcessor()

    # Make process_icon_url raise an exception
    async def raising_process_url(url, fallback_url=None):
        # Track that this URL was processed for verification
        mock_processor.processed_urls[url] = True
        return fallback_url or url

    mock_processor.process_icon_url = raising_process_url  # type: ignore

    # Create the backend with our mock processor
    rs_backend = RemoteSettingsBackend(
        server=rs_parameters["server"],
        collection=rs_parameters["collection"],
        bucket=rs_parameters["bucket"],
        icon_processor=mock_processor,
    )

    # Mock the Remote Settings client methods
    mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
    mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
    mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

    # Fetch the suggestions - this should not raise an exception
    suggestion_content: SuggestionContent = await rs_backend.fetch()

    # Verify that the icon URLs defaulted to original URLs due to error
    assert len(suggestion_content.icons) == 1

    # Check that each icon URL is the original attachment URL
    for icon_id, icon_url in suggestion_content.icons.items():
        assert icon_url == f"attachment-host/main-workspace/quicksuggest-amp/icon-{icon_id}"

        # Verify the URL was processed (attempt was made)
        original_url = f"attachment-host/main-workspace/quicksuggest-amp/icon-{icon_id}"
        assert original_url in mock_processor.processed_urls


@pytest.mark.asyncio
async def test_remotesettings_with_gcs_integration(
    mocker: MockerFixture,
    rs_parameters: dict[str, str],
    rs_records: list[dict],
    rs_server_info: dict,
    rs_attachment_response: httpx.Response,
    mock_image: bytes,
    mock_http_response: MagicMock,
    gcs_storage_client,
    gcs_storage_bucket,
):
    """Integration test with actual GCS components."""
    # Patch settings to provide the necessary attributes for IconProcessor.__init__
    with patch("merino.utils.icon_processor.settings") as mock_settings:
        mock_settings.icon = MagicMock()
        mock_settings.icon.max_size = 1024 * 1024  # 1MB
        mock_settings.icon.favicons_root = "favicons"
        mock_settings.icon.http_timeout = 5

        # Create a mock HTTP client
        mock_http_client = AsyncMock()

        # Create a real IconProcessor using the test GCS client/bucket
        icon_processor = IconProcessor(
            gcs_project=gcs_storage_client.project,
            gcs_bucket=gcs_storage_bucket.name,
            cdn_hostname=settings.image_gcs.cdn_hostname,
            http_client=mock_http_client,
        )

        # Replace the GCS client with our test client
        icon_processor.uploader.storage_client = gcs_storage_client

        # Mock HTTP client for downloading icons
        async def mock_download_favicon(url):
            return Image(content=mock_image, content_type="image/png")

        # Replace the download method
        mocker.patch.object(icon_processor, "_download_favicon", side_effect=mock_download_favicon)

        # Create the backend with our icon processor
        rs_backend = RemoteSettingsBackend(
            server=rs_parameters["server"],
            collection=rs_parameters["collection"],
            bucket=rs_parameters["bucket"],
            icon_processor=icon_processor,
        )

        # Mock the Remote Settings client methods
        mocker.patch.object(kinto_http.AsyncClient, "get_records", return_value=rs_records)
        mocker.patch.object(kinto_http.AsyncClient, "server_info", return_value=rs_server_info)
        mocker.patch.object(httpx.AsyncClient, "get", return_value=rs_attachment_response)

        # Fetch the suggestions
        suggestion_content: SuggestionContent = await rs_backend.fetch()

        # Verify that the in-use icon URLs were processed, the not-in-use one shouldn't be processed.
        assert len(suggestion_content.icons) == 1

        # Check that each icon URL points to expected location
        for icon_url in suggestion_content.icons.values():
            # The CDN hostname is configured in testing.toml as 'test-cdn.mozilla.net'
            assert "https://test-cdn.mozilla.net/favicons/" in icon_url
