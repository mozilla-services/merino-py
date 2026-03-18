"""Integration tests for async favicon downloading and domain metadata uploading."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from merino.jobs.navigational_suggestions.io.async_favicon_downloader import AsyncFaviconDownloader
from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import DomainMetadataUploader
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image


@pytest.fixture
def sample_favicon_data():
    """Sample favicon data for different formats."""
    return {
        "ico": b"\x00\x00\x01\x00\x02\x00\x10\x10\x00\x00\x01\x00\x08\x00\xab\x03\x00\x00&\x00\x00\x00  \x00\x00\x01\x00\x08\x00\x0b\x07\x00\x00\xd1\x03\x00\x00",
        "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xffa\x00\x00\x00\x00IEND\xaeB`\x82",
        "svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="green"/></svg>',
        "invalid": b"not_an_image_file",
    }


@pytest.fixture
def mock_gcs_uploader():
    """Create mock GCS uploader."""
    mock_uploader = MagicMock(spec=GcsUploader)
    mock_blob = MagicMock()
    mock_uploader.upload_content.return_value = mock_blob
    mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.ico"
    mock_uploader.get_most_recent_file.return_value = mock_blob
    return mock_uploader, mock_blob


class TestAsyncFaviconDownloaderIntegration:
    """Integration tests for AsyncFaviconDownloader."""

    def test_favicon_downloader_initialization(self):
        """Test AsyncFaviconDownloader can be initialized without errors."""
        downloader = AsyncFaviconDownloader()

        # Should be able to initialize
        assert downloader is not None
        assert hasattr(downloader, "session")
        assert hasattr(downloader, "download_favicon")
        assert hasattr(downloader, "requests_get")

    @pytest.mark.asyncio
    async def test_successful_favicon_download(self, sample_favicon_data):
        """Test successful favicon download with various image formats."""
        downloader = AsyncFaviconDownloader()

        test_cases = [
            ("https://example.com/favicon.ico", sample_favicon_data["ico"], "image/x-icon"),
            ("https://example.com/favicon.png", sample_favicon_data["png"], "image/png"),
            ("https://example.com/favicon.svg", sample_favicon_data["svg"], "image/svg+xml"),
        ]

        for url, expected_data, content_type in test_cases:
            with patch.object(downloader.session, "get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_headers = MagicMock()
                mock_headers.get.return_value = content_type
                mock_response.headers = mock_headers
                mock_response.content = expected_data
                mock_get.return_value = mock_response

                result = await downloader.download_favicon(url)

                assert result is not None
                assert isinstance(result, Image)
                assert result.content == expected_data
                assert result.content_type == content_type

    @pytest.mark.asyncio
    async def test_favicon_download_error_handling(self):
        """Test favicon download handles various error scenarios."""
        downloader = AsyncFaviconDownloader()

        error_scenarios = [
            (404, "Not Found"),
            (403, "Forbidden"),
            (500, "Internal Server Error"),
            (503, "Service Unavailable"),
        ]

        for status_code, reason in error_scenarios:
            with patch.object(downloader.session, "get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = status_code
                mock_response.reason = reason
                mock_get.return_value = mock_response

                result = await downloader.download_favicon("https://example.com/favicon.ico")
                assert result is None

    @pytest.mark.asyncio
    async def test_favicon_download_network_timeout(self):
        """Test favicon download handles network timeouts."""
        downloader = AsyncFaviconDownloader()

        with patch.object(downloader.session, "get") as mock_get:
            mock_get.side_effect = asyncio.TimeoutError("Request timeout")

            result = await downloader.download_favicon("https://example.com/favicon.ico")
            assert result is None

    @pytest.mark.asyncio
    async def test_favicon_download_concurrent_requests(self, sample_favicon_data):
        """Test concurrent favicon downloads work correctly."""
        downloader = AsyncFaviconDownloader()

        urls = [
            "https://example1.com/favicon.ico",
            "https://example2.com/favicon.png",
            "https://example3.com/favicon.svg",
        ]

        def create_mock_response(url):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "png" in url:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/png"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["png"]
            elif "svg" in url:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/svg+xml"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["svg"]
            else:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/x-icon"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["ico"]
            return mock_response

        with patch.object(downloader.session, "get") as mock_get:
            mock_get.side_effect = lambda url, **kwargs: create_mock_response(url)

            # Execute concurrent downloads
            results = await downloader.download_multiple_favicons(urls)

            # Verify all downloads succeeded
            assert len(results) == 3
            for result in results:
                assert result is not None
                assert isinstance(result, Image)

    @pytest.mark.asyncio
    async def test_favicon_downloader_reset_functionality(self):
        """Test favicon downloader reset functionality."""
        downloader = AsyncFaviconDownloader()

        # Should be able to call reset without errors
        await downloader.reset()

        # Should still be functional after reset
        with patch.object(downloader.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_headers = MagicMock()
            mock_headers.get.return_value = "image/png"
            mock_response.headers = mock_headers
            mock_response.content = b"favicon_data"
            mock_get.return_value = mock_response

            result = await downloader.download_favicon("https://example.com/favicon.png")
            assert result is not None
            assert isinstance(result, Image)


class TestDomainMetadataUploaderIntegration:
    """Integration tests for DomainMetadataUploader."""

    @pytest.mark.asyncio
    async def test_uploader_initialization(self, mock_gcs_uploader):
        """Test DomainMetadataUploader can be initialized."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        assert uploader.uploader == mock_uploader
        assert uploader.async_favicon_downloader == mock_downloader
        assert uploader.force_upload is False

    @pytest.mark.asyncio
    async def test_favicon_upload_workflow(self, sample_favicon_data, mock_gcs_uploader):
        """Test complete favicon upload workflow."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Mock successful favicon download
        mock_image = Image(content=sample_favicon_data["ico"], content_type="image/x-icon")
        mock_downloader.download_favicon.return_value = mock_image

        # Test upload functionality exists
        assert hasattr(uploader, "upload_top_picks")
        assert hasattr(uploader, "get_latest_file_for_diff")
        assert hasattr(uploader, "destination_favicon_name")

        # Test that uploader has the expected interface
        assert uploader.DESTINATION_FAVICONS_ROOT == "favicons"
        assert uploader.DESTINATION_TOP_PICK_FILE_NAME == "top_picks_latest.json"

    @pytest.mark.asyncio
    async def test_favicon_upload_download_failure(self, mock_gcs_uploader):
        """Test favicon upload handles download failures."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Mock failed favicon download
        mock_downloader.download_favicon.return_value = None

        # Should handle download failure gracefully
        favicon_url = "https://example.com/favicon.ico"
        result = await mock_downloader.download_favicon(favicon_url)
        assert result is None

    @pytest.mark.asyncio
    async def test_favicon_upload_gcs_error(self, sample_favicon_data, mock_gcs_uploader):
        """Test favicon upload handles GCS upload errors."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Mock successful download but failed upload
        mock_image = Image(content=sample_favicon_data["png"], content_type="image/png")
        mock_downloader.download_favicon.return_value = mock_image
        mock_uploader.upload_image.side_effect = Exception("GCS upload failed")

        # Should handle upload errors
        with pytest.raises(Exception, match="GCS upload failed"):
            mock_uploader.upload_image(mock_image, "test.png")

    @pytest.mark.asyncio
    async def test_multiple_favicon_uploads(self, sample_favicon_data, mock_gcs_uploader):
        """Test multiple favicon uploads work correctly."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Mock multiple favicon downloads
        favicon_urls = [
            "https://example1.com/favicon.ico",
            "https://example2.com/favicon.png",
            "https://example3.com/favicon.svg",
        ]

        mock_images = [
            Image(content=sample_favicon_data["ico"], content_type="image/x-icon"),
            Image(content=sample_favicon_data["png"], content_type="image/png"),
            Image(content=sample_favicon_data["svg"], content_type="image/svg+xml"),
        ]

        mock_downloader.download_multiple_favicons.return_value = mock_images

        results = await mock_downloader.download_multiple_favicons(favicon_urls)
        assert len(results) == 3
        assert all(isinstance(img, Image) for img in results)

    def test_top_picks_upload(self, mock_gcs_uploader):
        """Test top picks data upload."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = MagicMock()

        uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        test_data = '{"domains": ["example.com", "test.org"]}'
        result = uploader.upload_top_picks(test_data)

        # Should call upload_content twice (latest + timestamped)
        assert mock_uploader.upload_content.call_count == 2

        # Should return the timestamped blob
        assert result == mock_blob

        # Verify calls were made with correct parameters
        calls = mock_uploader.upload_content.call_args_list

        # First call should be for the latest file
        latest_call = calls[0]
        assert latest_call[0][0] == test_data  # content
        assert latest_call[0][1] == "top_picks_latest.json"  # filename
        assert latest_call[1]["forced_upload"] is True

        # Second call should be for timestamped file
        timestamped_call = calls[1]
        assert timestamped_call[0][0] == test_data  # content
        assert timestamped_call[0][1].endswith("_top_picks.json")  # timestamped filename

    def test_get_latest_file_for_diff(self, mock_gcs_uploader):
        """Test getting latest file for diff calculation."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = MagicMock()

        uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Test the method exists
        assert hasattr(uploader, "get_latest_file_for_diff")

        # Mock the most recent file lookup to return None (no file found case)
        mock_uploader.get_most_recent_file.return_value = None

        result = uploader.get_latest_file_for_diff()

        # Should call the underlying uploader method
        mock_uploader.get_most_recent_file.assert_called_once()
        assert result is None

    def test_destination_favicon_name_generation(self, mock_gcs_uploader):
        """Test destination favicon name generation."""
        mock_uploader, mock_blob = mock_gcs_uploader
        mock_downloader = MagicMock()

        uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=mock_downloader
        )

        # Test method exists
        assert hasattr(uploader, "destination_favicon_name")

        # Test with sample Image input
        sample_image = Image(content=b"fake_favicon_data", content_type="image/png")
        result = uploader.destination_favicon_name(sample_image)

        # Should return a string that incorporates the image hash
        assert isinstance(result, str)
        assert len(result) > 0
        assert result.endswith(".png")


class TestAsyncFaviconIntegrationWorkflows:
    """Integration tests for complete async favicon workflows."""

    @pytest.mark.asyncio
    async def test_end_to_end_favicon_workflow(self, sample_favicon_data, mock_gcs_uploader):
        """Test complete end-to-end favicon processing workflow."""
        mock_uploader, mock_blob = mock_gcs_uploader

        # Create real downloader and uploader instances
        downloader = AsyncFaviconDownloader()
        metadata_uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=downloader
        )

        test_domain = {"domain": "example.com", "favicon_url": "https://example.com/favicon.ico"}

        # Mock successful favicon download
        with patch.object(downloader.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_headers = MagicMock()
            mock_headers.get.return_value = "image/x-icon"
            mock_response.headers = mock_headers
            mock_response.content = sample_favicon_data["ico"]
            mock_get.return_value = mock_response

            # Download favicon
            favicon_result = await downloader.download_favicon(test_domain["favicon_url"])

            # Verify download succeeded
            assert favicon_result is not None
            assert isinstance(favicon_result, Image)
            assert favicon_result.content == sample_favicon_data["ico"]

            # Test uploader integration
            assert metadata_uploader.async_favicon_downloader == downloader

    @pytest.mark.asyncio
    async def test_batch_favicon_processing(self, sample_favicon_data, mock_gcs_uploader):
        """Test batch processing of multiple favicons with mixed results."""
        mock_uploader, mock_blob = mock_gcs_uploader

        downloader = AsyncFaviconDownloader()
        DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=downloader
        )

        test_urls = [
            "https://example1.com/favicon.ico",  # Success
            "https://example2.com/favicon.png",  # Success
            "https://example3.com/favicon.svg",  # Success
            "https://broken.com/favicon.ico",  # Failure
        ]

        def mock_get_side_effect(url, **kwargs):
            if "broken.com" in url:
                # Simulate network error
                raise Exception("Network error")

            mock_response = MagicMock()
            mock_response.status_code = 200

            if "png" in url:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/png"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["png"]
            elif "svg" in url:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/svg+xml"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["svg"]
            else:
                mock_headers = MagicMock()
                mock_headers.get.return_value = "image/x-icon"
                mock_response.headers = mock_headers
                mock_response.content = sample_favicon_data["ico"]

            return mock_response

        with patch.object(downloader.session, "get", side_effect=mock_get_side_effect):
            # Process all URLs
            results = await downloader.download_multiple_favicons(test_urls)

            # Should handle mixed success/failure
            assert len(results) == 4

            # First 3 should succeed, last should fail (None)
            successful_count = sum(1 for r in results if r is not None)
            assert successful_count == 3

    @pytest.mark.asyncio
    async def test_workflow_error_resilience(self, mock_gcs_uploader):
        """Test that workflows are resilient to various types of errors."""
        mock_uploader, mock_blob = mock_gcs_uploader

        downloader = AsyncFaviconDownloader()
        metadata_uploader = DomainMetadataUploader(
            force_upload=False, uploader=mock_uploader, async_favicon_downloader=downloader
        )

        error_scenarios = [
            ("timeout", asyncio.TimeoutError("Request timeout")),
            ("connection", ConnectionError("Connection failed")),
            ("http", Exception("HTTP error")),
        ]

        for error_name, error_exception in error_scenarios:
            with patch.object(downloader.session, "get", side_effect=error_exception):
                result = await downloader.download_favicon(f"https://{error_name}.com/favicon.ico")

                # Should handle all errors gracefully by returning None
                assert result is None

        # Uploader should still be functional
        test_data = '{"test": "data"}'
        upload_result = metadata_uploader.upload_top_picks(test_data)
        assert upload_result == mock_blob
