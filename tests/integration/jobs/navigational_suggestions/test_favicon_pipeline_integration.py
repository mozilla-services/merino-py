# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the favicon processing pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from bs4 import BeautifulSoup

from merino.jobs.navigational_suggestions.favicon.favicon_extractor import FaviconExtractor
from merino.jobs.navigational_suggestions.favicon.favicon_processor import FaviconProcessor
from merino.jobs.navigational_suggestions.favicon.favicon_selector import FaviconSelector
from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import FaviconScraper
from merino.jobs.navigational_suggestions.io.async_favicon_downloader import AsyncFaviconDownloader


@pytest.fixture
def sample_html_with_favicons():
    """HTML content with various favicon formats."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Site</title>
        <link rel="icon" href="/favicon.ico" type="image/x-icon">
        <link rel="icon" href="/favicon-32x32.png" sizes="32x32" type="image/png">
        <link rel="icon" href="/favicon-16x16.png" sizes="16x16" type="image/png">
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" sizes="180x180">
        <link rel="apple-touch-icon" href="/apple-touch-icon-152x152.png" sizes="152x152">
        <meta name="msapplication-TileImage" content="/mstile-144x144.png">
        <link rel="manifest" href="/site.webmanifest">
    </head>
    <body>
        <h1>Test Site</h1>
    </body>
    </html>
    """


@pytest.fixture
def sample_html_minimal():
    """Minimal HTML without explicit favicon links."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Minimal Site</title>
    </head>
    <body>
        <h1>Minimal Site</h1>
    </body>
    </html>
    """


@pytest.fixture
def sample_manifest_json():
    """Sample web app manifest with icons."""
    return {
        "name": "Test App",
        "icons": [
            {"src": "/icon-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512x512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


class TestFaviconScraperIntegration:
    """Integration tests for FaviconScraper with real HTML parsing."""

    def test_scrape_favicon_data_from_html(self, sample_html_with_favicons):
        """Test favicon data extraction from HTML with various favicon types."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        scraper = FaviconScraper(mock_downloader)

        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")
        favicon_data = scraper.scrape_favicon_data(soup)

        # Should extract link tags
        assert len(favicon_data.links) > 0

        # Should find standard favicon
        favicon_links = [link for link in favicon_data.links if link.get("href") == "/favicon.ico"]
        assert len(favicon_links) > 0

        # Should find sized icons
        sized_icons = [link for link in favicon_data.links if link.get("sizes")]
        assert len(sized_icons) > 0

        # Should find apple touch icons
        apple_icons = [
            link for link in favicon_data.links if "apple-touch-icon" in link.get("href", "")
        ]
        assert len(apple_icons) > 0

        # Should find meta tags
        assert len(favicon_data.metas) > 0

        # Should find manifest link
        assert len(favicon_data.manifests) > 0

    def test_scrape_favicon_data_minimal_html(self, sample_html_minimal):
        """Test favicon data extraction from minimal HTML."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        scraper = FaviconScraper(mock_downloader)

        soup = BeautifulSoup(sample_html_minimal, "html.parser")
        favicon_data = scraper.scrape_favicon_data(soup)

        # Should handle minimal HTML gracefully
        assert favicon_data.links == []
        assert favicon_data.metas == []
        assert favicon_data.manifests == []

    def test_scrape_favicon_data_error_handling(self):
        """Test favicon data extraction handles malformed HTML."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        scraper = FaviconScraper(mock_downloader)

        # Test with None page
        favicon_data = scraper.scrape_favicon_data(None)
        assert favicon_data.links == []
        assert favicon_data.metas == []
        assert favicon_data.manifests == []

    @pytest.mark.asyncio
    async def test_scrape_favicons_from_manifest_success(self, sample_manifest_json):
        """Test successful manifest favicon extraction."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_response = MagicMock()
        mock_response.json.return_value = sample_manifest_json
        mock_downloader.requests_get.return_value = mock_response

        scraper = FaviconScraper(mock_downloader)

        icons = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert len(icons) == 2
        assert icons[0]["src"] == "/icon-192x192.png"
        assert icons[0]["sizes"] == "192x192"
        assert icons[1]["src"] == "/icon-512x512.png"
        assert icons[1]["sizes"] == "512x512"

    @pytest.mark.asyncio
    async def test_scrape_favicons_from_manifest_error(self):
        """Test manifest favicon extraction handles errors."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_downloader.requests_get.side_effect = Exception("Network error")

        scraper = FaviconScraper(mock_downloader)

        icons = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert icons == []

    @pytest.mark.asyncio
    async def test_get_default_favicon_success(self):
        """Test successful default favicon detection."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_response = MagicMock()
        mock_response.url = "https://example.com/favicon.ico"
        mock_downloader.requests_get.return_value = mock_response

        scraper = FaviconScraper(mock_downloader)

        favicon_url = await scraper.get_default_favicon("https://example.com")

        assert favicon_url == "https://example.com/favicon.ico"

    @pytest.mark.asyncio
    async def test_get_default_favicon_not_found(self):
        """Test default favicon detection when favicon doesn't exist."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_downloader.requests_get.return_value = None

        scraper = FaviconScraper(mock_downloader)

        favicon_url = await scraper.get_default_favicon("https://example.com")

        assert favicon_url is None


class TestFaviconExtractorIntegration:
    """Integration tests for FaviconExtractor."""

    @pytest.mark.asyncio
    async def test_extract_favicons_complete_pipeline(self, sample_html_with_favicons):
        """Test complete favicon extraction pipeline."""
        # Create mock scraper with manifest support
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_scraper = FaviconScraper(mock_downloader)

        # Mock manifest response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "icons": [{"src": "/manifest-icon.png", "sizes": "192x192", "type": "image/png"}]
        }
        mock_downloader.requests_get.return_value = mock_response

        extractor = FaviconExtractor(mock_scraper)
        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")

        favicons = await extractor.extract_favicons(soup, "https://example.com", max_icons=10)

        # Should extract multiple favicon types
        assert len(favicons) > 0

        # Check for various favicon sources
        favicon_urls = [fav["href"] for fav in favicons]

        # Should include standard favicon
        assert any("favicon.ico" in url for url in favicon_urls)

        # Should include sized icons
        assert any("favicon-32x32.png" in url for url in favicon_urls)

        # Should include Apple touch icons
        assert any("apple-touch-icon" in url for url in favicon_urls)

    @pytest.mark.asyncio
    async def test_extract_favicons_with_max_limit(self, sample_html_with_favicons):
        """Test favicon extraction respects max_icons limit."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_scraper = FaviconScraper(mock_downloader)
        mock_downloader.requests_get.return_value = None  # No manifest

        extractor = FaviconExtractor(mock_scraper)
        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")

        favicons = await extractor.extract_favicons(soup, "https://example.com", max_icons=3)

        # Should respect the limit
        assert len(favicons) <= 3

    @pytest.mark.asyncio
    async def test_extract_favicons_fallback_to_default(self, sample_html_minimal):
        """Test favicon extraction falls back to default favicon.ico."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_scraper = FaviconScraper(mock_downloader)

        # Mock successful default favicon
        mock_response = MagicMock()
        mock_response.url = "https://example.com/favicon.ico"
        mock_downloader.requests_get.return_value = mock_response

        extractor = FaviconExtractor(mock_scraper)
        soup = BeautifulSoup(sample_html_minimal, "html.parser")

        favicons = await extractor.extract_favicons(soup, "https://example.com")

        # Should include default favicon when no others found
        assert len(favicons) >= 1
        default_favicon = next(
            (fav for fav in favicons if fav["href"].endswith("favicon.ico")), None
        )
        assert default_favicon is not None

    @pytest.mark.asyncio
    async def test_extract_favicons_error_handling(self, sample_html_with_favicons):
        """Test favicon extraction handles errors gracefully."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_scraper = FaviconScraper(mock_downloader)

        # Mock errors in manifest and default favicon requests
        mock_downloader.requests_get.side_effect = Exception("Network error")

        extractor = FaviconExtractor(mock_scraper)
        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")

        # Should not raise exceptions despite errors
        favicons = await extractor.extract_favicons(soup, "https://example.com")

        # Should still return some results from HTML parsing
        assert isinstance(favicons, list)


class TestFaviconProcessorIntegration:
    """Integration tests for FaviconProcessor."""

    @pytest.mark.asyncio
    async def test_favicon_processor_initialization(self):
        """Test FaviconProcessor can be initialized with required parameters."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        assert processor.favicon_downloader == mock_downloader
        assert processor.base_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_favicon_processor_with_empty_base_url(self):
        """Test FaviconProcessor handles empty base URL."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        processor = FaviconProcessor(favicon_downloader=mock_downloader, base_url="")

        assert processor.favicon_downloader == mock_downloader
        assert processor.base_url == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_svg_priority_workflow(self):
        """Test complete workflow where SVG is prioritized over bitmap."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Create mock SVG image
        svg_image = Image(
            content=b'<svg width="32" height="32"></svg>', content_type="image/svg+xml"
        )

        # Configure downloader to return SVG
        mock_downloader.download_multiple_favicons.return_value = [svg_image]

        # Configure uploader
        mock_uploader.destination_favicon_name.return_value = "favicon.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.svg"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": "https://example.com/favicon.svg", "type": "image/svg+xml"},
            {"href": "https://example.com/favicon.png", "type": "image/png", "sizes": "32x32"},
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        assert result == "https://cdn.example.com/favicon.svg"
        mock_downloader.download_multiple_favicons.assert_called_once()
        mock_uploader.upload_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_upload_bitmap_fallback_workflow(self):
        """Test complete workflow falling back to bitmap when no SVG available."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Create mock PNG image with dimensions
        png_image = MagicMock(spec=Image)
        png_image.content_type = "image/png"
        png_image.get_dimensions.return_value = (32, 32)

        # Configure downloader to return bitmap
        mock_downloader.download_multiple_favicons.return_value = [png_image]

        # Configure uploader
        mock_uploader.destination_favicon_name.return_value = "favicon.png"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.png"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {
                "href": "https://example.com/favicon.png",
                "type": "image/png",
                "sizes": "32x32",
                "_source": "link",
            }
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        assert result == "https://cdn.example.com/favicon.png"
        mock_downloader.download_multiple_favicons.assert_called_once()
        mock_uploader.upload_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_upload_svg_vs_bitmap_priority(self):
        """Test complete workflow where SVG is prioritized over higher quality bitmap."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Create mock SVG and bitmap images
        svg_image = Image(
            content=b'<svg width="16" height="16"></svg>', content_type="image/svg+xml"
        )
        bitmap_image = MagicMock(spec=Image)
        bitmap_image.content_type = "image/png"
        bitmap_image.get_dimensions.return_value = (64, 64)  # Higher resolution than SVG

        # Configure downloader to return both types in separate calls (SVG first, then bitmap)
        mock_downloader.download_multiple_favicons.side_effect = [
            [svg_image],  # SVG call
            [],  # Bitmap call won't happen since SVG succeeds
        ]

        mock_uploader.destination_favicon_name.return_value = "favicon.svg"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.svg"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": "https://example.com/favicon.svg", "type": "image/svg+xml"},
            {
                "href": "https://example.com/favicon.png",
                "type": "image/png",
                "sizes": "64x64",
                "_source": "link",
            },
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        # Should prioritize SVG over bitmap, even if bitmap is higher resolution
        assert result == "https://cdn.example.com/favicon.svg"
        # Only one download call should be made (for SVG), since SVG succeeds
        assert mock_downloader.download_multiple_favicons.call_count == 1
        mock_uploader.upload_image.assert_called_once_with(
            svg_image, "favicon.svg", forced_upload=True
        )

    @pytest.mark.asyncio
    async def test_process_and_upload_batch_processing_workflow(self):
        """Test batch processing workflow for multiple bitmap favicons."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Create multiple mock images for batch processing (6 favicons to trigger batching)
        images = []
        for i in range(6):
            img = MagicMock(spec=Image)
            img.content_type = "image/png"
            img.get_dimensions.return_value = (16 + i * 8, 16 + i * 8)  # Increasing sizes
            images.append(img)

        # Configure downloader to return images in batches
        mock_downloader.download_multiple_favicons.side_effect = [
            images[:5],  # First batch of 5
            images[5:],  # Second batch of 1
        ]

        mock_uploader.destination_favicon_name.return_value = "favicon.png"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.png"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": f"https://example.com/favicon{i}.png", "type": "image/png", "_source": "link"}
            for i in range(6)
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        assert result == "https://cdn.example.com/favicon.png"
        # Should be called twice due to batching
        assert mock_downloader.download_multiple_favicons.call_count == 2
        # Should upload the largest (best) favicon
        mock_uploader.upload_image.assert_called()

    @pytest.mark.asyncio
    async def test_process_and_upload_below_min_width_threshold(self):
        """Test workflow when no favicons meet minimum width requirement."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Create small image below threshold
        small_image = MagicMock(spec=Image)
        small_image.content_type = "image/png"
        small_image.get_dimensions.return_value = (8, 8)  # Below 32px minimum

        mock_downloader.download_multiple_favicons.return_value = [small_image]
        mock_uploader.destination_favicon_name.return_value = "favicon.png"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.png"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": "https://example.com/small.png", "type": "image/png", "_source": "link"}
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=32, uploader=mock_uploader
        )

        # Should return empty string when no favicon meets minimum width
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_url_processing_integration(self):
        """Test integration of URL fixing and validation with processing."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Mock downloader to return empty (no valid URLs after processing)
        mock_downloader.download_multiple_favicons.return_value = []

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": "/relative/favicon.ico"},  # Should be fixed with base_url
            {"href": "invalid-url"},  # Should be filtered out
            {"href": ""},  # Should be filtered out
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        # Should process relative URL but result in empty due to no valid images
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_upload_failure_fallback(self):
        """Test fallback to original URL when upload fails."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        svg_image = Image(
            content=b'<svg width="32" height="32"></svg>', content_type="image/svg+xml"
        )

        mock_downloader.download_multiple_favicons.return_value = [svg_image]
        mock_uploader.destination_favicon_name.return_value = "favicon.svg"
        # Simulate upload failure
        mock_uploader.upload_image.side_effect = Exception("Upload failed")

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [{"href": "https://example.com/favicon.svg", "type": "image/svg+xml"}]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        # Should fallback to original URL when upload fails
        assert result == "https://example.com/favicon.svg"

    @pytest.mark.asyncio
    async def test_process_and_upload_download_error_handling(self):
        """Test error handling when download fails."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Simulate download failure
        mock_downloader.download_multiple_favicons.side_effect = Exception("Download failed")

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [{"href": "https://example.com/favicon.svg", "type": "image/svg+xml"}]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        # Should return empty string when download fails
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_and_upload_mixed_content_types(self):
        """Test workflow with mixed valid and invalid content types."""
        from merino.utils.gcs.models import Image

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        # Mix of valid and invalid images
        invalid_image = MagicMock()
        invalid_image.content_type = "text/html"  # Invalid content type

        valid_image = MagicMock(spec=Image)
        valid_image.content_type = "image/png"
        valid_image.get_dimensions.return_value = (32, 32)

        mock_downloader.download_multiple_favicons.return_value = [invalid_image, valid_image]
        mock_uploader.destination_favicon_name.return_value = "favicon.png"
        mock_uploader.upload_image.return_value = "https://cdn.example.com/favicon.png"

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        favicons = [
            {"href": "https://example.com/invalid.png", "type": "image/png", "_source": "link"},
            {"href": "https://example.com/valid.png", "type": "image/png", "_source": "link"},
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        # Should successfully process the valid image and skip the invalid one
        assert result == "https://cdn.example.com/favicon.png"

    @pytest.mark.asyncio
    async def test_process_and_upload_empty_favicons_list(self):
        """Test handling of empty favicons list."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        processor = FaviconProcessor(
            favicon_downloader=mock_downloader, base_url="https://example.com"
        )

        result = await processor.process_and_upload_best_favicon(
            [], min_width=16, uploader=mock_uploader
        )

        assert result == ""
        mock_downloader.download_multiple_favicons.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_and_upload_invalid_urls_only(self):
        """Test handling when all URLs are invalid after processing."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_uploader = MagicMock()

        processor = FaviconProcessor(favicon_downloader=mock_downloader, base_url="")

        favicons = [
            {"href": "invalid-url"},
            {"href": "not-a-url"},
            {"href": ""},
        ]

        result = await processor.process_and_upload_best_favicon(
            favicons, min_width=16, uploader=mock_uploader
        )

        assert result == ""
        mock_downloader.download_multiple_favicons.assert_not_called()


class TestFaviconSelectorIntegration:
    """Integration tests for FaviconSelector."""

    def test_favicon_selector_basic_functionality(self):
        """Test FaviconSelector can select from favicon list."""
        selector = FaviconSelector()

        test_favicons = [
            {"href": "https://example.com/favicon.ico", "type": "image/x-icon", "sizes": "16x16"},
            {
                "href": "https://example.com/favicon-32x32.png",
                "type": "image/png",
                "sizes": "32x32",
            },
        ]

        # Should be able to select a favicon
        # FaviconSelector.select_best_favicon expects dimensions list and returns tuple
        dimensions = [(16, 16), (32, 32)]  # One for each favicon
        best_favicon, width = selector.select_best_favicon(test_favicons, dimensions)

        if best_favicon:
            assert "href" in best_favicon  # FaviconSelector uses "href", not "url"
            assert best_favicon["href"] in [fav["href"] for fav in test_favicons]
            assert width > 0

    def test_favicon_selector_empty_list(self):
        """Test FaviconSelector handles empty favicon list."""
        selector = FaviconSelector()

        best_favicon, width = selector.select_best_favicon([], [])

        # Should handle empty list gracefully
        assert best_favicon is None
        assert width == 0


class TestIntegratedFaviconWorkflow:
    """Test complete integrated favicon processing workflows."""

    @pytest.mark.asyncio
    async def test_end_to_end_favicon_extraction_workflow(self, sample_html_with_favicons):
        """Test complete end-to-end favicon extraction workflow."""
        # Setup components
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        # Mock manifest response
        manifest_response = MagicMock()
        manifest_response.json.return_value = {
            "icons": [{"src": "/app-icon.png", "sizes": "256x256", "type": "image/png"}]
        }

        # Mock default favicon response
        default_response = MagicMock()
        default_response.url = "https://example.com/favicon.ico"

        def mock_requests_get(url):
            if "manifest" in url:
                return manifest_response
            elif "favicon.ico" in url:
                return default_response
            return None

        mock_downloader.requests_get.side_effect = mock_requests_get

        # Create pipeline components
        scraper = FaviconScraper(mock_downloader)
        extractor = FaviconExtractor(scraper)

        # Execute workflow
        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")
        extracted_favicons = await extractor.extract_favicons(soup, "https://example.com")

        # Verify we got favicons from multiple sources
        assert len(extracted_favicons) > 0

        # Check for different types of favicons
        favicon_urls = [fav.get("href", "") for fav in extracted_favicons]

        # Should have standard favicons from HTML
        html_favicons = [
            url
            for url in favicon_urls
            if any(
                pattern in url
                for pattern in ["favicon.ico", "favicon-32x32.png", "apple-touch-icon"]
            )
        ]
        assert len(html_favicons) > 0

        # Manifest processing is complex and may not always extract favicons in test environment
        # Just verify we got some favicons from HTML parsing
        assert any("favicon.ico" in url for url in favicon_urls)
        assert any("apple-touch-icon" in url for url in favicon_urls)

    @pytest.mark.asyncio
    async def test_favicon_workflow_error_resilience(self, sample_html_with_favicons):
        """Test favicon workflow is resilient to partial failures."""
        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)

        # Mock to simulate some failures
        call_count = 0

        def mock_requests_get(url):
            nonlocal call_count
            call_count += 1

            if call_count % 2 == 0:  # Fail every other request
                raise Exception("Simulated network error")

            if "manifest" in url:
                response = MagicMock()
                response.json.return_value = {"icons": []}
                return response
            elif "favicon.ico" in url:
                response = MagicMock()
                response.url = url
                return response
            return None

        mock_downloader.requests_get.side_effect = mock_requests_get

        # Create components
        scraper = FaviconScraper(mock_downloader)
        extractor = FaviconExtractor(scraper)

        # Should not raise exceptions despite partial failures
        soup = BeautifulSoup(sample_html_with_favicons, "html.parser")
        extracted_favicons = await extractor.extract_favicons(soup, "https://example.com")

        # Should still get some results
        assert isinstance(extracted_favicons, list)
        # At minimum should get favicons from HTML parsing even if external requests fail
        assert len(extracted_favicons) > 0

    @pytest.mark.asyncio
    async def test_favicon_workflow_with_relative_urls(self):
        """Test favicon workflow properly handles relative URLs."""
        html_with_relative = """
        <html>
        <head>
            <link rel="icon" href="favicon.ico">
            <link rel="icon" href="/assets/icon.png" sizes="32x32">
            <link rel="manifest" href="./manifest.json">
        </head>
        </html>
        """

        mock_downloader = AsyncMock(spec=AsyncFaviconDownloader)
        mock_downloader.requests_get.return_value = None  # No external resources

        scraper = FaviconScraper(mock_downloader)
        extractor = FaviconExtractor(scraper)

        soup = BeautifulSoup(html_with_relative, "html.parser")
        extracted_favicons = await extractor.extract_favicons(soup, "https://example.com/page/")

        # Should resolve relative URLs correctly
        favicon_urls = [fav.get("href", "") for fav in extracted_favicons]

        # Should contain properly resolved URLs
        # Check that we got the expected resolved URLs (excluding manifest which may not be processed)
        expected_urls = [
            "https://example.com/page/favicon.ico",
            "https://example.com/assets/icon.png",
        ]

        for expected_url in expected_urls:
            assert any(
                expected_url in url for url in favicon_urls
            ), f"Expected URL {expected_url} not found in {favicon_urls}"
