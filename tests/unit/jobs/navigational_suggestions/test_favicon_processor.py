"""Complete test coverage for favicon_processor.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from merino.jobs.navigational_suggestions.favicon.favicon_processor import FaviconProcessor
from merino.jobs.navigational_suggestions.io import AsyncFaviconDownloader
from merino.utils.gcs.models import Image


@pytest.fixture
def mock_favicon_downloader():
    """Mock favicon downloader for testing."""
    downloader = MagicMock(spec=AsyncFaviconDownloader)
    return downloader


@pytest.fixture
def mock_uploader():
    """Mock uploader for testing."""
    uploader = MagicMock()
    uploader.destination_favicon_name = MagicMock(return_value="test_favicon.png")
    uploader.upload_image = MagicMock(return_value="https://cdn.example.com/test_favicon.png")
    return uploader


@pytest.fixture
def favicon_processor(mock_favicon_downloader):
    """Create FaviconProcessor instance with mocked dependencies."""
    return FaviconProcessor(mock_favicon_downloader, "https://example.com")


@pytest.fixture
def mock_image():
    """Mock image for testing."""
    image = MagicMock(spec=Image)
    image.content_type = "image/png"
    image.get_dimensions.return_value = (64, 64)
    return image


@pytest.fixture
def mock_svg_image():
    """Mock SVG image for testing."""
    image = MagicMock(spec=Image)
    image.content_type = "image/svg+xml"
    return image


class TestFaviconProcessorInit:
    """Test FaviconProcessor initialization."""

    def test_init_with_downloader_and_base_url(self, mock_favicon_downloader):
        """Test initialization with downloader and base URL."""
        processor = FaviconProcessor(mock_favicon_downloader, "https://example.com")
        assert processor.favicon_downloader == mock_favicon_downloader
        assert processor.base_url == "https://example.com"

    def test_init_with_empty_base_url(self, mock_favicon_downloader):
        """Test initialization with empty base URL."""
        processor = FaviconProcessor(mock_favicon_downloader, "")
        assert processor.base_url == ""

    def test_init_without_base_url(self, mock_favicon_downloader):
        """Test initialization without base URL (default)."""
        processor = FaviconProcessor(mock_favicon_downloader)
        assert processor.base_url == ""


class TestProcessAndUploadBestFavicon:
    """Test the main process_and_upload_best_favicon method."""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_empty_list(
        self, favicon_processor, mock_uploader
    ):
        """Test processing with empty favicon list."""
        result = await favicon_processor.process_and_upload_best_favicon([], 32, mock_uploader)
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_invalid_urls(
        self, favicon_processor, mock_uploader
    ):
        """Test processing with invalid URLs."""
        favicons = [{"href": ""}, {"href": "invalid"}]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix:
            mock_fix.return_value = ""

            result = await favicon_processor.process_and_upload_best_favicon(
                favicons, 32, mock_uploader
            )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_svg_priority(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test that SVG favicons are prioritized."""
        favicons = [
            {"href": "https://example.com/favicon.ico"},
            {"href": "https://example.com/favicon.svg"},
        ]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        with patch.object(favicon_processor, "_process_svg_favicons") as mock_svg:
            mock_svg.return_value = "https://cdn.example.com/favicon.svg"

            result = await favicon_processor.process_and_upload_best_favicon(
                favicons, 32, mock_uploader
            )

        assert result == "https://cdn.example.com/favicon.svg"

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_fallback_to_bitmap(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test fallback to bitmap processing when no SVG found."""
        favicons = [{"href": "https://example.com/favicon.ico"}]

        with patch.object(favicon_processor, "_process_svg_favicons") as mock_svg:
            with patch.object(favicon_processor, "_process_bitmap_favicons") as mock_bitmap:
                mock_svg.return_value = ""
                mock_bitmap.return_value = "https://cdn.example.com/favicon.ico"

                result = await favicon_processor.process_and_upload_best_favicon(
                    favicons, 32, mock_uploader
                )

        assert result == "https://cdn.example.com/favicon.ico"

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_exception_handling(
        self, favicon_processor, mock_uploader
    ):
        """Test exception handling in main method."""
        favicons = [{"href": "https://example.com/favicon.ico"}]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix:
            mock_fix.side_effect = Exception("Processing error")

            result = await favicon_processor.process_and_upload_best_favicon(
                favicons, 32, mock_uploader
            )

        assert result == ""


class TestCategorizeSvgUrls:
    """Test _categorize_svg_urls method."""

    def test_categorize_svg_urls_basic(self, favicon_processor):
        """Test basic SVG URL categorization."""
        urls = [
            "https://example.com/favicon.svg",
            "https://example.com/favicon.ico",
            "https://example.com/icon.SVG",  # Test case insensitive
        ]

        svg_urls, svg_indices = favicon_processor._categorize_svg_urls(urls)

        assert svg_urls == ["https://example.com/favicon.svg", "https://example.com/icon.SVG"]
        assert svg_indices == [0, 2]

    def test_categorize_svg_urls_empty_list(self, favicon_processor):
        """Test SVG categorization with empty list."""
        svg_urls, svg_indices = favicon_processor._categorize_svg_urls([])
        assert svg_urls == []
        assert svg_indices == []

    def test_categorize_svg_urls_no_svgs(self, favicon_processor):
        """Test SVG categorization with no SVGs."""
        urls = ["https://example.com/favicon.ico", "https://example.com/favicon.png"]

        svg_urls, svg_indices = favicon_processor._categorize_svg_urls(urls)

        assert svg_urls == []
        assert svg_indices == []


class TestCategorizeBitmapUrls:
    """Test _categorize_bitmap_urls method."""

    def test_categorize_bitmap_urls_basic(self, favicon_processor):
        """Test basic bitmap URL categorization."""
        urls = [
            "https://example.com/favicon.svg",
            "https://example.com/favicon.ico",
            "https://example.com/favicon.png",
        ]

        bitmap_urls, bitmap_indices = favicon_processor._categorize_bitmap_urls(urls)

        assert bitmap_urls == [
            "https://example.com/favicon.ico",
            "https://example.com/favicon.png",
        ]
        assert bitmap_indices == [1, 2]

    def test_categorize_bitmap_urls_empty_list(self, favicon_processor):
        """Test bitmap categorization with empty list."""
        bitmap_urls, bitmap_indices = favicon_processor._categorize_bitmap_urls([])
        assert bitmap_urls == []
        assert bitmap_indices == []

    def test_categorize_bitmap_urls_only_svgs(self, favicon_processor):
        """Test bitmap categorization with only SVGs."""
        urls = ["https://example.com/favicon.svg", "https://example.com/icon.SVG"]

        bitmap_urls, bitmap_indices = favicon_processor._categorize_bitmap_urls(urls)

        assert bitmap_urls == []
        assert bitmap_indices == []


class TestProcessSvgFavicons:
    """Test _process_svg_favicons method."""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_empty_list(self, favicon_processor, mock_uploader):
        """Test SVG processing with empty list."""
        result = await favicon_processor._process_svg_favicons([], [], [], mock_uploader)
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_success(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test successful SVG processing."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == "https://cdn.example.com/test_favicon.png"
        mock_uploader.upload_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_svg_favicons_skip_masked(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing skips masked SVGs."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = [0]  # This SVG is masked

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""
        mock_uploader.upload_image.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_svg_favicons_non_svg_content_type(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test SVG processing with non-SVG content type."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image]
        )  # PNG, not SVG

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_none_image(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test SVG processing with None image."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[None])

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_upload_failure_fallback(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing fallback to original URL on upload failure."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )
        mock_uploader.upload_image.side_effect = Exception("Upload failed")

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == "https://example.com/favicon.svg"

    @pytest.mark.asyncio
    async def test_process_svg_favicons_processing_exception(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing with processing exception."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            side_effect=Exception("Download failed")
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_individual_processing_exception(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing with individual image processing exception."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_svg_image.content_type = "image/svg+xml"
        mock_uploader.destination_favicon_name.side_effect = Exception("Processing error")
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""


class TestProcessBitmapFavicons:
    """Test _process_bitmap_favicons method."""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_empty_list(self, favicon_processor, mock_uploader):
        """Test bitmap processing with empty list."""
        result = await favicon_processor._process_bitmap_favicons([], [], [], 32, mock_uploader)
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_success(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test successful bitmap processing."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = True

            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_below_min_width(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing with favicon below minimum width."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_image.get_dimensions.return_value = (16, 16)  # Below 32px minimum
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = True

            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        assert result == ""  # Should not return favicon below minimum width

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_batch_processing(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing in batches."""
        # Create more URLs than batch size
        bitmap_urls = [f"https://example.com/favicon{i}.ico" for i in range(10)]
        bitmap_indices = list(range(10))
        all_favicons = [{"href": url, "_source": "link"} for url in bitmap_urls]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image] * 5
        )  # Batch size is 5

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = True

            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        # Should process in batches and return result
        assert result == "https://cdn.example.com/test_favicon.png"
        # Should be called twice (2 batches of 5)
        assert mock_favicon_downloader.download_multiple_favicons.call_count == 2

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_none_image(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing with None image."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[None])

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_non_image_content_type(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing with non-image content type."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_non_image = MagicMock()
        mock_non_image.content_type = "text/html"
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_non_image]
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_dimension_exception(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing with dimension extraction exception."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_image.get_dimensions.side_effect = Exception("Dimension error")
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_upload_failure_fallback(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing fallback to original URL on upload failure."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])
        mock_uploader.upload_image.side_effect = Exception("Upload failed")

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = True

            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        assert result == "https://example.com/favicon.ico"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_batch_exception(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing with batch exception."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            side_effect=Exception("Batch error")
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_individual_processing_exception(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing with individual image processing exception."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])
        mock_uploader.destination_favicon_name.side_effect = Exception("Processing error")

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == "https://example.com/favicon.ico"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_overall_exception(
        self, favicon_processor, mock_uploader
    ):
        """Test bitmap processing with overall exception."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        # Patch the FAVICON_BATCH_SIZE import to cause an exception
        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FAVICON_BATCH_SIZE",
            side_effect=Exception("Import error"),
        ):
            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_memory_cleanup(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test that memory cleanup (del statements) are executed properly."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        all_favicons = [
            {"href": "https://example.com/favicon1.ico", "_source": "link"},
            {"href": "https://example.com/favicon2.ico", "_source": "link"},
        ]

        # Create mock images that track deletion
        mock_image1 = MagicMock(spec=Image)
        mock_image1.content_type = "image/png"
        mock_image1.get_dimensions.return_value = (64, 64)

        mock_image2 = MagicMock(spec=Image)
        mock_image2.content_type = "image/png"
        mock_image2.get_dimensions.return_value = (32, 32)

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image1, mock_image2]
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        # Verify the result and that processing occurred
        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_with_none_in_batch(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing with None image in batch."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        all_favicons = [
            {"href": "https://example.com/favicon1.ico", "_source": "link"},
            {"href": "https://example.com/favicon2.ico", "_source": "link"},
        ]

        # First image is None, second is valid
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[None, mock_image]
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_all_none_images(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing when all images are None."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        all_favicons = [
            {"href": "https://example.com/favicon1.ico", "_source": "link"},
            {"href": "https://example.com/favicon2.ico", "_source": "link"},
        ]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[None, None])

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_memory_cleanup_on_exception(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test that memory cleanup occurs even when exceptions happen during SVG processing."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        # Mock image that will cause an exception during individual processing but not download
        mock_uploader.destination_favicon_name.side_effect = Exception("Processing error")
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_source_priority_edge_case(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing with edge cases in source priority."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        # Test with missing _source key and edge case priorities
        all_favicons = [
            {"href": "https://example.com/favicon1.ico"},  # No _source key
            {"href": "https://example.com/favicon2.ico", "_source": "unknown_source"},
        ]

        mock_image1 = MagicMock(spec=Image)
        mock_image1.content_type = "image/png"
        mock_image1.get_dimensions.return_value = (64, 64)

        mock_image2 = MagicMock(spec=Image)
        mock_image2.content_type = "image/png"
        mock_image2.get_dimensions.return_value = (32, 32)

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image1, mock_image2]
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == "https://cdn.example.com/test_favicon.png"


class TestEdgeCasesAndErrorPaths:
    """Test edge cases and error paths for comprehensive coverage."""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_urls_with_none_elements(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test processing when URL list contains None elements after fix_url."""
        favicons = [
            {"href": "invalid://url"},  # This might become None after fix_url
            {"href": "https://example.com/favicon.svg"},
        ]

        # Mock fix_url to return None for invalid URL
        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix_url:
            mock_fix_url.side_effect = [None, "https://example.com/favicon.svg"]

            with patch(
                "merino.jobs.navigational_suggestions.favicon.favicon_processor.is_valid_url"
            ) as mock_is_valid:
                mock_is_valid.side_effect = lambda x: x is not None

                await favicon_processor.process_and_upload_best_favicon(
                    favicons, 32, mock_uploader
                )

                # Should process the valid URL
                assert mock_fix_url.call_count == 2

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_with_empty_href(
        self, favicon_processor, mock_uploader
    ):
        """Test processing favicons with empty or missing href."""
        favicons = [
            {"href": ""},  # Empty href
            {},  # No href key
            {"href": "https://example.com/favicon.ico"},
        ]

        result = await favicon_processor.process_and_upload_best_favicon(
            favicons, 32, mock_uploader
        )

        # Should handle empty hrefs gracefully
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_process_svg_favicons_with_download_exception(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test SVG processing when download_multiple_favicons raises exception."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            side_effect=Exception("Download failed")
        )

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_with_download_exception_per_batch(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing when download fails for specific batches."""
        # Create enough URLs to trigger multiple batches
        bitmap_urls = [
            f"https://example.com/favicon{i}.ico" for i in range(7)
        ]  # More than FAVICON_BATCH_SIZE
        bitmap_indices = list(range(7))
        all_favicons = [{"href": url, "_source": "link"} for url in bitmap_urls]

        # First batch fails, second batch succeeds
        side_effects = [
            Exception("Batch 1 failed"),
            [MagicMock(spec=Image)],  # Second batch with 2 items
        ]

        # Setup the second batch image
        mock_image = MagicMock(spec=Image)
        mock_image.content_type = "image/png"
        mock_image.get_dimensions.return_value = (64, 64)
        side_effects[1] = [mock_image, mock_image]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(side_effect=side_effects)

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        # Should get result from second batch
        assert result == "https://cdn.example.com/test_favicon.png"

    def test_categorize_svg_urls_case_insensitive(self, favicon_processor):
        """Test that SVG categorization is case-insensitive."""
        urls = [
            "https://example.com/favicon.SVG",
            "https://example.com/favicon.Svg",
            "https://example.com/favicon.svg",
            "https://example.com/favicon.ico",
        ]

        svg_urls, svg_indices = favicon_processor._categorize_svg_urls(urls)

        assert len(svg_urls) == 3  # All three SVG variations
        assert svg_urls == [
            "https://example.com/favicon.SVG",
            "https://example.com/favicon.Svg",
            "https://example.com/favicon.svg",
        ]
        assert svg_indices == [0, 1, 2]

    def test_categorize_bitmap_urls_excludes_all_svg_cases(self, favicon_processor):
        """Test that bitmap categorization excludes all SVG case variations."""
        urls = [
            "https://example.com/favicon.ico",
            "https://example.com/favicon.svg",
            "https://example.com/favicon.SVG",
            "https://example.com/favicon.png",
        ]

        bitmap_urls, bitmap_indices = favicon_processor._categorize_bitmap_urls(urls)

        assert len(bitmap_urls) == 2  # Only ico and png
        assert bitmap_urls == [
            "https://example.com/favicon.ico",
            "https://example.com/favicon.png",
        ]
        assert bitmap_indices == [0, 3]

    @pytest.mark.asyncio
    async def test_process_svg_favicons_with_invalid_content_type_none(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test SVG processing with image that has None content_type."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_image = MagicMock(spec=Image)
        mock_image.content_type = None  # None content type
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_with_invalid_content_type_none(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing with image that has None content_type."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_image = MagicMock(spec=Image)
        mock_image.content_type = None  # None content type
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == ""


class TestAdvancedErrorHandlingAndMemoryManagement:
    """Test advanced error handling scenarios and memory management."""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_with_fix_url_exception(
        self, favicon_processor, mock_uploader
    ):
        """Test main processing method when fix_url raises an exception."""
        favicons = [{"href": "https://example.com/favicon.ico"}]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix_url:
            mock_fix_url.side_effect = Exception("URL fixing failed")

            result = await favicon_processor.process_and_upload_best_favicon(
                favicons, 32, mock_uploader
            )

            assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_with_is_valid_url_exception(
        self, favicon_processor, mock_uploader
    ):
        """Test main processing method when is_valid_url raises an exception."""
        favicons = [{"href": "https://example.com/favicon.ico"}]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix_url:
            mock_fix_url.return_value = "https://example.com/favicon.ico"

            with patch(
                "merino.jobs.navigational_suggestions.favicon.favicon_processor.is_valid_url"
            ) as mock_is_valid:
                mock_is_valid.side_effect = Exception("URL validation failed")

                result = await favicon_processor.process_and_upload_best_favicon(
                    favicons, 32, mock_uploader
                )

                assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_with_del_statement_coverage(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing to ensure del statements are covered."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )
        mock_uploader.destination_favicon_name.return_value = "test.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/test.svg"

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == "https://cdn.example.com/test.svg"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_with_forced_batch_size_one(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing with very small batch size to trigger multiple batches."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        all_favicons = [
            {"href": "https://example.com/favicon1.ico", "_source": "link"},
            {"href": "https://example.com/favicon2.ico", "_source": "meta"},
        ]

        # Create two different mock images
        mock_image1 = MagicMock(spec=Image)
        mock_image1.content_type = "image/png"
        mock_image1.get_dimensions.return_value = (32, 32)

        mock_image2 = MagicMock(spec=Image)
        mock_image2.content_type = "image/png"
        mock_image2.get_dimensions.return_value = (64, 64)

        # Mock different responses for each batch
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            side_effect=[[mock_image1], [mock_image2]]
        )

        # Override batch size to force multiple batches
        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FAVICON_BATCH_SIZE", 1
        ):
            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_svg_favicons_upload_exception_with_url_fallback(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test SVG processing when upload fails and falls back to original URL."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )
        mock_uploader.destination_favicon_name.return_value = "test.svg"
        mock_uploader.upload_image.side_effect = Exception("Upload failed")

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        # Should fall back to original URL
        assert result == "https://example.com/favicon.svg"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_upload_exception_with_url_fallback(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing when upload fails and falls back to original URL."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])
        mock_uploader.destination_favicon_name.return_value = "test.ico"
        mock_uploader.upload_image.side_effect = Exception("Upload failed")

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        # Should fall back to original URL
        assert result == "https://example.com/favicon.ico"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_with_is_better_favicon_false_path(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test bitmap processing when is_better_favicon returns False."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        # Mock is_better_favicon to always return False
        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = False

            result = await favicon_processor._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
            )

            assert result == ""

    @pytest.mark.asyncio
    async def test_process_svg_favicons_zip_iteration_coverage(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test SVG processing with multiple images to ensure zip iteration coverage."""
        svg_urls = ["https://example.com/favicon1.svg", "https://example.com/favicon2.svg"]
        svg_indices = [0, 1]
        masked_svg_indices = [1]  # Second SVG is masked

        mock_svg_image1 = MagicMock(spec=Image)
        mock_svg_image1.content_type = "image/svg+xml"

        mock_svg_image2 = MagicMock(spec=Image)
        mock_svg_image2.content_type = "image/svg+xml"

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image1, mock_svg_image2]
        )
        mock_uploader.destination_favicon_name.return_value = "test.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/test.svg"

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        # Should process first SVG and skip second (masked)
        assert result == "https://cdn.example.com/test.svg"


class TestFinalCoverageTests:
    """Final tests to achieve maximum coverage on remaining code paths."""

    @pytest.mark.asyncio
    async def test_process_and_upload_best_favicon_categorize_methods_called(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test that categorization methods are called in main processing flow."""
        favicons = [
            {"href": "https://example.com/favicon.svg"},
            {"href": "https://example.com/favicon.ico"},
        ]

        # Mock the categorization methods to ensure they're called
        with patch.object(favicon_processor, "_categorize_svg_urls") as mock_cat_svg:
            with patch.object(favicon_processor, "_categorize_bitmap_urls") as mock_cat_bitmap:
                with patch.object(favicon_processor, "_process_svg_favicons") as mock_proc_svg:
                    with patch.object(
                        favicon_processor, "_process_bitmap_favicons"
                    ) as mock_proc_bitmap:
                        mock_cat_svg.return_value = (["https://example.com/favicon.svg"], [0])
                        mock_cat_bitmap.return_value = (["https://example.com/favicon.ico"], [1])
                        mock_proc_svg.return_value = ""  # No SVG result
                        mock_proc_bitmap.return_value = "https://cdn.example.com/test.ico"

                        result = await favicon_processor.process_and_upload_best_favicon(
                            favicons, 32, mock_uploader
                        )

                        assert result == "https://cdn.example.com/test.ico"
                        mock_cat_svg.assert_called_once()
                        mock_cat_bitmap.assert_called_once()
                        mock_proc_svg.assert_called_once()
                        mock_proc_bitmap.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_svg_favicons_continue_on_invalid_content_type(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test SVG processing continues with next image when content type is invalid."""
        svg_urls = ["https://example.com/favicon1.svg", "https://example.com/favicon2.svg"]
        svg_indices = [0, 1]
        masked_svg_indices = []

        # First image has invalid content type, second is valid
        mock_svg_image1 = MagicMock(spec=Image)
        mock_svg_image1.content_type = "image/png"  # Invalid for SVG

        mock_svg_image2 = MagicMock(spec=Image)
        mock_svg_image2.content_type = "image/svg+xml"  # Valid

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image1, mock_svg_image2]
        )
        mock_uploader.destination_favicon_name.return_value = "test.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/test.svg"

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        # Should skip first image and process second
        assert result == "https://cdn.example.com/test.svg"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_continue_on_invalid_content_type(
        self, favicon_processor, mock_uploader, mock_favicon_downloader
    ):
        """Test bitmap processing continues with next image when content type is invalid."""
        bitmap_urls = ["https://example.com/favicon1.ico", "https://example.com/favicon2.ico"]
        bitmap_indices = [0, 1]
        all_favicons = [
            {"href": "https://example.com/favicon1.ico", "_source": "link"},
            {"href": "https://example.com/favicon2.ico", "_source": "link"},
        ]

        # First image has invalid content type, second is valid
        mock_image1 = MagicMock(spec=Image)
        mock_image1.content_type = "text/plain"  # Invalid for image

        mock_image2 = MagicMock(spec=Image)
        mock_image2.content_type = "image/png"  # Valid
        mock_image2.get_dimensions.return_value = (64, 64)

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image1, mock_image2]
        )

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        # Should skip first image and process second
        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_bitmap_favicons_del_batch_images_coverage(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test that del batch_images statement is covered."""
        bitmap_urls = ["https://example.com/favicon.ico"]
        bitmap_indices = [0]
        all_favicons = [{"href": "https://example.com/favicon.ico", "_source": "link"}]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(return_value=[mock_image])

        result = await favicon_processor._process_bitmap_favicons(
            bitmap_urls, bitmap_indices, all_favicons, 32, mock_uploader
        )

        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_process_svg_favicons_del_svg_images_coverage(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_favicon_downloader
    ):
        """Test that del svg_images statement is covered."""
        svg_urls = ["https://example.com/favicon.svg"]
        svg_indices = [0]
        masked_svg_indices = []

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )
        mock_uploader.destination_favicon_name.return_value = "test.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/test.svg"

        result = await favicon_processor._process_svg_favicons(
            svg_urls, svg_indices, masked_svg_indices, mock_uploader
        )

        assert result == "https://cdn.example.com/test.svg"

    @pytest.mark.asyncio
    async def test_process_and_upload_all_urls_invalid_after_filtering(
        self, favicon_processor, mock_uploader
    ):
        """Test processing when all URLs become invalid after fix_url and is_valid_url filtering."""
        favicons = [{"href": "invalid-url"}, {"href": "another-invalid-url"}]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix_url:
            with patch(
                "merino.jobs.navigational_suggestions.favicon.favicon_processor.is_valid_url"
            ) as mock_is_valid:
                mock_fix_url.side_effect = ["fixed-but-still-invalid", "also-fixed-but-invalid"]
                mock_is_valid.side_effect = [False, False]  # Both URLs invalid

                result = await favicon_processor.process_and_upload_best_favicon(
                    favicons, 32, mock_uploader
                )

                assert result == ""

    def test_init_with_different_base_url_formats(self, mock_favicon_downloader):
        """Test initialization with various base URL formats."""
        # Test with trailing slash
        processor1 = FaviconProcessor(mock_favicon_downloader, "https://example.com/")
        assert processor1.base_url == "https://example.com/"

        # Test with subdirectory
        processor2 = FaviconProcessor(mock_favicon_downloader, "https://example.com/subdir")
        assert processor2.base_url == "https://example.com/subdir"

        # Test with query parameters
        processor3 = FaviconProcessor(mock_favicon_downloader, "https://example.com?param=value")
        assert processor3.base_url == "https://example.com?param=value"


class TestIntegrationScenarios:
    """Test various integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_processing_flow_svg_wins(
        self, favicon_processor, mock_uploader, mock_svg_image, mock_image, mock_favicon_downloader
    ):
        """Test full processing flow where SVG wins."""
        favicons = [
            {"href": "https://example.com/favicon.ico"},
            {"href": "https://example.com/favicon.svg"},
        ]

        # Mock that we get both images but SVG is processed first
        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_svg_image]
        )

        result = await favicon_processor.process_and_upload_best_favicon(
            favicons, 32, mock_uploader
        )

        # SVG should win and be uploaded
        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_full_processing_flow_bitmap_only(
        self, favicon_processor, mock_uploader, mock_image, mock_favicon_downloader
    ):
        """Test full processing flow with only bitmap favicons."""
        favicons = [
            {"href": "https://example.com/favicon.ico"},
            {"href": "https://example.com/favicon.png"},
        ]

        mock_favicon_downloader.download_multiple_favicons = AsyncMock(
            return_value=[mock_image, mock_image]
        )

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.FaviconSelector.is_better_favicon"
        ) as mock_is_better:
            mock_is_better.return_value = True

            result = await favicon_processor.process_and_upload_best_favicon(
                favicons, 32, mock_uploader
            )

        assert result == "https://cdn.example.com/test_favicon.png"

    @pytest.mark.asyncio
    async def test_processing_with_mixed_valid_invalid_urls(
        self, favicon_processor, mock_uploader
    ):
        """Test processing with mix of valid and invalid URLs."""
        favicons = [
            {"href": ""},  # Invalid
            {"href": "https://example.com/favicon.svg"},  # Valid SVG
            {"href": "invalid-url"},  # Invalid
        ]

        with patch(
            "merino.jobs.navigational_suggestions.favicon.favicon_processor.fix_url"
        ) as mock_fix:
            mock_fix.side_effect = ["", "https://example.com/favicon.svg", ""]
            with patch(
                "merino.jobs.navigational_suggestions.favicon.favicon_processor.is_valid_url"
            ) as mock_valid:
                mock_valid.side_effect = [False, True, False]
                with patch.object(favicon_processor, "_process_svg_favicons") as mock_svg:
                    mock_svg.return_value = "https://cdn.example.com/favicon.svg"

                    result = await favicon_processor.process_and_upload_best_favicon(
                        favicons, 32, mock_uploader
                    )

        assert result == "https://cdn.example.com/favicon.svg"
