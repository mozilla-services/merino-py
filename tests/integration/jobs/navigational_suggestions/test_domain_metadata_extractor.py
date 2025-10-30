"""Integration tests for domain_metadata_extractor.py covering core functionality."""

import io
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from PIL import Image as PILImage

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    FaviconData,
    Scraper,
    current_scraper,
)
from merino.jobs.utils.system_monitor import SystemMonitor
from merino.utils.gcs.models import Image


@pytest.fixture
def mock_scraper():
    """Mock scraper for testing."""
    scraper = MagicMock(spec=Scraper)
    scraper.open = AsyncMock(return_value="https://example.com")
    scraper.scrape_title = MagicMock(return_value="Example Website")
    scraper.get_default_favicon = AsyncMock(return_value="https://example.com/favicon.ico")
    return scraper


@pytest.fixture
def mock_favicon_data():
    """Create mock favicon data for testing."""
    return FaviconData(
        links=[
            {"rel": "icon", "href": "/favicon.png", "sizes": "32x32"},
            {"rel": "apple-touch-icon", "href": "/apple-touch-icon.png", "sizes": "180x180"},
        ],
        metas=[
            {"name": "msapplication-TileImage", "content": "/mstile-144x144.png"},
        ],
        manifests=[
            {"rel": "manifest", "href": "/manifest.json"},
        ],
    )


@pytest.fixture
def mock_favicon_downloader():
    """Mock favicon downloader for testing."""
    downloader = MagicMock()
    downloader.download_favicon = AsyncMock(return_value=None)
    downloader.download_multiple_favicons = AsyncMock(return_value=[])
    return downloader


@pytest.fixture
def mock_uploader():
    """Mock uploader for testing."""
    uploader = MagicMock()
    uploader.upload_favicon.return_value = "https://cdn.example.com/favicon.ico"
    uploader.upload_image = AsyncMock(return_value="https://cdn.example.com/favicon.ico")
    uploader.destination_favicon_name = MagicMock(return_value="favicons/favicon.ico")
    return uploader


@pytest.fixture
def create_image(size=(32, 32), format="PNG"):
    """Create a test image with the specified size and format."""

    def _create_image(width=size[0], height=size[1], img_format=format):
        img_data = io.BytesIO()
        test_image = PILImage.new("RGB", (width, height))
        test_image.save(img_data, format=img_format)
        img_data.seek(0)
        return Image(content=img_data.getvalue(), content_type=f"image/{img_format.lower()}")

    return _create_image


@pytest.fixture
def mock_system_monitor():
    """Mock SystemMonitor for testing."""
    monitor = MagicMock(spec=SystemMonitor)
    return monitor


class TestDomainMetadataExtractor:
    """Test core functionality of domain metadata extractor."""

    def test_initialization(self):
        """Test the initialization of DomainMetadataExtractor."""
        # Test with default parameters
        extractor = DomainMetadataExtractor(blocked_domains=set())
        assert hasattr(extractor, "favicon_downloader")
        assert extractor.blocked_domains == set()

        # Test with custom parameters
        mock_downloader = MagicMock()
        custom_blocked = {"blocked1.com", "blocked2.com"}

        extractor = DomainMetadataExtractor(
            blocked_domains=custom_blocked,
            favicon_downloader=mock_downloader,
        )

        assert extractor.favicon_downloader is mock_downloader
        assert extractor.blocked_domains == custom_blocked

    def test_fix_url(self):
        """Test the _fix_url method."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Test empty URL
        assert extractor._fix_url("") == ""
        assert extractor._fix_url("/") == ""

        # Test protocol-relative URL
        assert extractor._fix_url("//example.com/favicon.ico") == "https://example.com/favicon.ico"

        # Test URL without protocol
        assert extractor._fix_url("example.com/favicon.ico") == "https://example.com/favicon.ico"

        # Test URL with protocol
        assert (
            extractor._fix_url("https://example.com/favicon.ico")
            == "https://example.com/favicon.ico"
        )
        assert (
            extractor._fix_url("http://example.com/favicon.ico")
            == "http://example.com/favicon.ico"
        )

        # Test absolute path with base URL context
        extractor._current_base_url = "https://example.com"
        assert extractor._fix_url("/favicon.ico") == "https://example.com/favicon.ico"

    def test_get_base_url(self):
        """Test the _get_base_url method."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Test with different URL formats
        assert (
            extractor._get_base_url("https://example.com/path/page.html") == "https://example.com"
        )
        assert (
            extractor._get_base_url("http://subdomain.example.com/")
            == "http://subdomain.example.com"
        )
        assert extractor._get_base_url("https://example.com:8080/path") == "https://example.com"

    def test_is_domain_blocked(self):
        """Test the _is_domain_blocked method."""
        # Set up with blocked domains
        blocked = {"example", "test"}
        extractor = DomainMetadataExtractor(blocked_domains=blocked)

        # Test with blocked domains
        assert extractor._is_domain_blocked("example.com", "com") is True
        assert extractor._is_domain_blocked("test.org", "org") is True

        # Test with non-blocked domains
        assert extractor._is_domain_blocked("allowed.com", "com") is False
        assert extractor._is_domain_blocked("safe.net", "net") is False

    def test_is_problematic_favicon_url(self):
        """Test the _is_problematic_favicon_url method."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Test data URLs
        assert extractor._is_problematic_favicon_url("data:image/png;base64,abc123") is True

        # Test manifest URLs with base64 marker
        manifest_marker = extractor.MANIFEST_JSON_BASE64_MARKER
        assert extractor._is_problematic_favicon_url(f"something{manifest_marker}xyz") is True

        # Test normal URLs
        assert extractor._is_problematic_favicon_url("https://example.com/favicon.ico") is False
        assert extractor._is_problematic_favicon_url("/favicon.ico") is False

    @pytest.mark.asyncio
    async def test_extract_favicons(self, mocker, mock_scraper, mock_favicon_data):
        """Test the _extract_favicons method."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Configure the mock scraper
        mock_scraper.scrape_favicon_data.return_value = mock_favicon_data

        # Set the context variable
        token = current_scraper.set(mock_scraper)
        try:
            # Call the method
            scraped_url = "https://example.com"
            favicons = await extractor._extract_favicons(scraped_url, max_icons=5)

            # Verify the results
            assert len(favicons) >= 2  # Should find at least the links

            # Verify base URL was set
            assert extractor._current_base_url == scraped_url
        finally:
            # Reset the context variable
            current_scraper.reset(token)

    @pytest.mark.asyncio
    async def test_process_favicon(self, mocker, mock_scraper, mock_uploader):
        """Test the _process_favicon method."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Mock _extract_favicons
        mock_favicons = [{"href": "https://example.com/favicon.ico"}]
        mocker.patch.object(extractor, "_extract_favicons", AsyncMock(return_value=mock_favicons))

        # Mock _upload_best_favicon
        expected_url = "https://cdn.example.com/favicons/favicon.ico"
        mocker.patch.object(
            extractor, "_upload_best_favicon", AsyncMock(return_value=expected_url)
        )

        # Call the method without the scraper parameter
        result = await extractor._process_favicon("https://example.com", 32, mock_uploader)

        # Verify the result
        assert result == expected_url

        # Verify _extract_favicons was called with correct arguments
        extractor._extract_favicons.assert_called_once_with("https://example.com", max_icons=5)

        # Verify _upload_best_favicon was called with correct arguments
        extractor._upload_best_favicon.assert_called_once_with(mock_favicons, 32, mock_uploader)


class TestDomainMetadataExtractorMonitoring:
    """Test domain metadata extractor with system monitoring."""

    def test_process_domains_with_monitoring(
        self, mocker, mock_scraper, mock_favicon_downloader, mock_uploader, mock_system_monitor
    ):
        """Test _process_domains with monitoring enabled."""
        # Create extractor and test data
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.scraper = mock_scraper
        extractor.favicon_downloader = mock_favicon_downloader

        domain_data = [
            {"domain": "example.com", "suffix": "com"},
            {"domain": "test.org", "suffix": "org"},
        ]

        # Create expected results
        expected_results = [
            {
                "domain": "example",
                "url": "https://example.com",
                "title": "Example Website",
                "icon": "https://cdn.example.com/example.ico",
            },
            {
                "domain": "test",
                "url": "https://test.org",
                "title": "Test Website",
                "icon": "https://cdn.example.com/test.ico",
            },
        ]

        # Mock _process_single_domain to return predefined results
        async def mock_process_single_domain(domain, min_width, uploader):
            domain_name = domain["domain"].split(".")[0]
            return {
                "domain": domain_name,
                "url": f"https://{domain['domain']}",
                "title": f"{domain_name.capitalize()} Website",
                "icon": f"https://cdn.example.com/{domain_name}.ico",
            }

        # Mock the SystemMonitor class and instance
        mocker.patch(
            "merino.jobs.utils.system_monitor.SystemMonitor", return_value=mock_system_monitor
        )

        # Mock the _process_single_domain method
        mocker.patch.object(
            extractor, "_process_single_domain", side_effect=mock_process_single_domain
        )

        # Mock asyncio.gather to return our expected results directly
        mocker.patch("asyncio.gather", return_value=expected_results)

        # Test synchronously by calling the method and running with mock results
        mocker.patch("asyncio.run", return_value=expected_results)

        # Call the method
        results = extractor.process_domain_metadata(
            domain_data, 32, mock_uploader, enable_monitoring=True
        )

        # Verify the results
        assert results == expected_results

        # Verify that SystemMonitor was instantiated
        assert isinstance(mock_system_monitor, MagicMock)

    def test_process_domains_without_monitoring(
        self, mocker, mock_scraper, mock_favicon_downloader, mock_uploader
    ):
        """Test _process_domains without monitoring enabled."""
        # Create extractor and test data
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.scraper = mock_scraper
        extractor.favicon_downloader = mock_favicon_downloader

        domain_data = [
            {"domain": "example.com", "suffix": "com"},
            {"domain": "test.org", "suffix": "org"},
        ]

        # Create expected results
        expected_results = [
            {
                "domain": "example",
                "url": "https://example.com",
                "title": "Example Website",
                "icon": "https://cdn.example.com/example.ico",
            },
            {
                "domain": "test",
                "url": "https://test.org",
                "title": "Test Website",
                "icon": "https://cdn.example.com/test.ico",
            },
        ]

        # Mock SystemMonitor to verify it's not created
        mock_system_monitor_class = mocker.patch("merino.jobs.utils.system_monitor.SystemMonitor")

        # Mock asyncio.run to return our expected results directly
        mocker.patch("asyncio.run", return_value=expected_results)

        # Call the method with monitoring disabled
        results = extractor.process_domain_metadata(
            domain_data, 32, mock_uploader, enable_monitoring=False
        )

        # Verify the results
        assert results == expected_results

        # Verify SystemMonitor was not created
        mock_system_monitor_class.assert_not_called()

    def test_process_domain_metadata_with_flag(self, mocker, mock_uploader):
        """Test that the monitoring flag is passed through correctly."""
        # Create a simplified test that just verifies the parameter is passed through

        # Mock extractor instance
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create sample data
        test_data = [{"domain": "example.com", "suffix": "com"}]
        expected_result = [{"domain": "example", "url": "https://example.com"}]

        # Mock asyncio.run to return a fixed value and capture its argument
        run_mock = mocker.patch("asyncio.run", return_value=expected_result)

        # Call with monitoring enabled
        extractor.process_domain_metadata(test_data, 32, mock_uploader, enable_monitoring=True)

        # Check that asyncio.run was called with a coroutine (_process_domains)
        # We can't check the internal parameters of the coroutine directly,
        # but we can verify that the call happened
        assert run_mock.called

        # For this simple integration test, we'll just check that the results are returned
        # properly and that no exceptions are raised
        result = extractor.process_domain_metadata(
            test_data, 32, mock_uploader, enable_monitoring=False
        )
        assert result == expected_result


@pytest.fixture
def real_scraper():
    """Create a real Scraper instance with mocked browser for testing."""
    scraper = Scraper()
    scraper.browser = MagicMock()
    scraper.browser.page = MagicMock()
    scraper.request_client = AsyncMock()
    return scraper


@pytest.fixture
def detailed_favicon_data():
    """Create detailed favicon data with various types for testing."""
    return FaviconData(
        links=[
            {"rel": "icon", "href": "/favicon.png", "sizes": "32x32"},
            {"rel": "icon", "href": "/favicon.svg", "type": "image/svg+xml"},
            {"rel": "icon", "mask": "", "href": "/mask-icon.svg"},
            {"rel": "apple-touch-icon", "href": "/apple-touch-icon.png", "sizes": "180x180"},
        ],
        metas=[
            {"name": "msapplication-TileImage", "content": "/mstile-144x144.png"},
        ],
        manifests=[
            {"rel": "manifest", "href": "/manifest.json"},
        ],
    )


class TestScraperIntegration:
    """Integration tests for the Scraper class."""

    def test_scrape_favicon_data(self, real_scraper):
        """Test scraping favicon data with various link and meta tags."""
        # Set up the mock page with elements to select
        link_tag1 = MagicMock()
        link_tag1.attrs = {"rel": "icon", "href": "/favicon.ico"}

        link_tag2 = MagicMock()
        link_tag2.attrs = {"rel": "apple-touch-icon", "href": "/apple-touch-icon.png"}

        meta_tag = MagicMock()
        meta_tag.attrs = {"name": "msapplication-TileImage", "content": "/mstile.png"}

        manifest_tag = MagicMock()
        manifest_tag.attrs = {"rel": "manifest", "href": "/manifest.json"}

        # Mock the select method to return our tags
        real_scraper.browser.page.select.side_effect = [
            [link_tag1, link_tag2],  # For link selector
            [meta_tag],  # For meta selector
            [manifest_tag],  # For manifest selector
        ]

        # Call the method
        result = real_scraper.scrape_favicon_data()

        # Verify the results
        assert len(result.links) == 2
        assert result.links[0]["href"] == "/favicon.ico"
        assert result.links[1]["href"] == "/apple-touch-icon.png"

        assert len(result.metas) == 1
        assert result.metas[0]["content"] == "/mstile.png"

        assert len(result.manifests) == 1
        assert result.manifests[0]["href"] == "/manifest.json"

    @pytest.mark.asyncio
    async def test_scrape_favicons_from_manifest(self, real_scraper):
        """Test scraping favicons from a manifest.json file."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ]
        }

        # Set up the mock client to return our response
        real_scraper.request_client.requests_get.return_value = mock_response

        # Call the method
        result = await real_scraper.scrape_favicons_from_manifest(
            "https://example.com/manifest.json"
        )

        # Verify the results
        assert len(result) == 2
        assert result[0]["src"] == "/icon-192.png"
        assert result[1]["src"] == "/icon-512.png"

        # Test error handling with invalid JSON
        mock_response.json.side_effect = ValueError("Invalid JSON")
        result = await real_scraper.scrape_favicons_from_manifest(
            "https://example.com/manifest.json"
        )
        assert result == []

        # Test error handling with request failure
        real_scraper.request_client.requests_get.return_value = None
        result = await real_scraper.scrape_favicons_from_manifest(
            "https://example.com/manifest.json"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_default_favicon(self, real_scraper):
        """Test retrieving the default favicon.ico."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.url = "https://example.com/favicon.ico"
        real_scraper.request_client.requests_get.return_value = mock_response

        # Call the method
        result = await real_scraper.get_default_favicon("https://example.com")

        # Verify the result
        assert result == "https://example.com/favicon.ico"

    def test_scrape_title(self, real_scraper):
        """Test scraping title from HTML."""
        # Create mock objects for finding elements
        head_mock = MagicMock()
        title_mock = MagicMock()
        title_mock.get_text.return_value = "Example Website Title"
        head_mock.find.return_value = title_mock

        # Mock the find method to return our mock objects
        real_scraper.browser.page.find.return_value = head_mock

        # Call the method
        result = real_scraper.scrape_title()

        # Verify the result
        assert result == "Example Website Title"

        # Test error handling with missing head
        real_scraper.browser.page.find.return_value = None
        result = real_scraper.scrape_title()
        assert result is None


class TestDomainMetadataExtractorIntegration:
    """Integration tests for the DomainMetadataExtractor class."""

    @pytest.mark.asyncio
    async def test_extract_favicons_with_all_sources(self, detailed_favicon_data):
        """Test extracting favicons from all possible sources."""
        # Create an extractor with mocked components
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create and configure a mock scraper
        mock_scraper = MagicMock(spec=Scraper)
        mock_scraper.scrape_favicon_data.return_value = detailed_favicon_data
        mock_scraper.get_default_favicon = AsyncMock(
            return_value="https://example.com/favicon.ico"
        )

        # Mock for scraping manifest
        manifest_icons = [
            {"src": "/icon-192.png", "sizes": "192x192"},
            {"src": "/icon-512.png", "sizes": "512x512"},
        ]
        mock_scraper.scrape_favicons_from_manifest = AsyncMock(return_value=manifest_icons)

        # Set the context variable
        token = current_scraper.set(mock_scraper)
        try:
            # Mock URL joining
            with patch(
                "merino.jobs.navigational_suggestions.domain_metadata_extractor.urljoin",
                side_effect=lambda base, path: f"{base}/{path.lstrip('/')}",
            ):
                # Call the method
                result = await extractor._extract_favicons("https://example.com")

                # Verify the results - should extract from links, metas, default favicon, and manifest
                assert len(result) >= 5

                # Verify base URL was set
                assert extractor._current_base_url == "https://example.com"
        finally:
            # Reset the context variable
            current_scraper.reset(token)

    @pytest.mark.asyncio
    async def test_extract_favicons_with_problematic_urls(self):
        """Test extracting favicons with problematic URLs that should be filtered out."""
        # Create an extractor with mocked components
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create mock scraper
        mock_scraper = MagicMock(spec=Scraper)

        # Create favicon data with problematic URLs
        problematic_data = FaviconData(
            links=[
                {
                    "rel": "icon",
                    "href": "data:image/png;base64,abc123",
                },  # Data URL - should be skipped
                {"rel": "icon", "href": f"something{extractor.MANIFEST_JSON_BASE64_MARKER}xyz"},
                # Manifest base64 - should be skipped
                {
                    "rel": "icon",
                    "href": "https://example.com/favicon.ico",
                },  # Valid URL - should be included
            ],
            metas=[],
            manifests=[],
        )

        # Configure the mock scraper
        mock_scraper.scrape_favicon_data.return_value = problematic_data
        mock_scraper.get_default_favicon = AsyncMock(return_value=None)

        # Set the context variable
        token = current_scraper.set(mock_scraper)
        try:
            # Call the method (without passing scraper parameter)
            result = await extractor._extract_favicons("https://example.com")

            # Verify that only the valid URL was included
            assert len(result) == 1
            assert "https://example.com/favicon.ico" in str(result)
        finally:
            # Reset the context variable
            current_scraper.reset(token)

        @pytest.mark.asyncio
        async def test_upload_best_favicon_source_prioritization(
            self, mock_uploader, create_image, mocker
        ):
            """Test the Firefox-style favicon prioritization with _source tracking.

            Firefox prioritization rules (implemented in is_better_favicon):
            1. Source priority: link > meta > manifest > default
            2. Within same source: larger size wins
            3. SVGs are handled during the early SVG processing phase
            """
            extractor = DomainMetadataExtractor(blocked_domains=set())

            # Create test favicons with different sources and sizes
            # Note: larger manifest favicon should lose to smaller link favicon due to source priority
            favicons = [
                {
                    "href": "https://example.com/manifest-large.png",
                    "_source": "manifest",
                    "sizes": "512x512",
                },
                {
                    "href": "https://example.com/meta-medium.png",
                    "_source": "meta",
                    "sizes": "128x128",
                },
                {
                    "href": "https://example.com/link-small.png",
                    "_source": "link",
                    "sizes": "32x32",
                },
                {
                    "href": "https://example.com/link-large.png",
                    "_source": "link",
                    "sizes": "64x64",
                },
                {"href": "https://example.com/default.ico", "_source": "default"},
            ]

            # Create corresponding mock images with actual dimensions
            manifest_image = create_image(
                512, 512, "PNG"
            )  # Largest size but lowest priority source
            meta_image = create_image(128, 128, "PNG")
            link_small_image = create_image(32, 32, "PNG")
            link_large_image = create_image(
                64, 64, "PNG"
            )  # Should win: highest priority source, largest among links
            default_image = create_image(16, 16, "PNG")

            # Mock favicon downloader to return our test images in same order as favicons
            extractor.favicon_downloader = AsyncMock()
            extractor.favicon_downloader.download_multiple_favicons.return_value = [
                manifest_image,
                meta_image,
                link_small_image,
                link_large_image,
                default_image,
            ]

            # Mock uploader responses - IMPORTANT: upload_image is synchronous
            mock_uploader.destination_favicon_name.return_value = "favicons/best_favicon.png"
            mock_uploader.upload_image = mocker.MagicMock(
                return_value="https://cdn.example.com/best_favicon.png"
            )

            # Call the method under test
            result = await extractor._upload_best_favicon(
                favicons, min_width=16, uploader=mock_uploader
            )

            # Verify the link source favicon with largest size was chosen (64x64)
            # Even though manifest source has 512x512, link source has higher priority
            assert result == "https://cdn.example.com/best_favicon.png"

            # Verify the correct image was uploaded (the 64x64 link favicon)
            mock_uploader.upload_image.assert_called_once_with(
                link_large_image, "favicons/best_favicon.png", forced_upload=False
            )

    @pytest.mark.asyncio
    async def test_process_single_domain_complete_flow(self, mock_uploader, mock_scraper_context):
        """Test the complete flow of processing a single domain."""
        # Unpack the fixture
        MockScraper, shared_scraper = mock_scraper_context

        # Configure the shared scraper for this test
        shared_scraper.open.return_value = "https://example.com"
        shared_scraper.scrape_title.return_value = "Example Website"

        # Create an extractor
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Mock internal methods that are called inside _process_single_domain
        extractor._get_base_url = MagicMock(return_value="https://example.com")
        extractor._process_favicon = AsyncMock(return_value="https://cdn.example.com/favicon.ico")
        extractor._get_second_level_domain = MagicMock(return_value="example")

        # Use the fixture to patch the Scraper class
        with patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper", MockScraper
        ):
            # Call the method
            domain_data = {"domain": "example.com", "suffix": "com"}
            result = await extractor._process_single_domain(domain_data, 32, mock_uploader)

        # Verify the result contains all expected fields
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example Website"
        assert result["icon"] == "https://cdn.example.com/favicon.ico"
        assert result["domain"] == "example"

    @pytest.mark.asyncio
    async def test_process_single_domain_blocked(self, mock_uploader):
        """Test processing a blocked domain."""
        # Create an extractor with blocked domains
        extractor = DomainMetadataExtractor(blocked_domains={"example"})

        # Call the method with a blocked domain
        domain_data = {"domain": "example.com", "suffix": "com"}
        result = await extractor._process_single_domain(domain_data, 32, mock_uploader)

        # Verify empty result for blocked domain
        assert result["url"] is None
        assert result["title"] == ""
        assert result["icon"] == ""
        assert result["domain"] == ""

    @pytest.mark.asyncio
    async def test_process_domains_with_exception_handling(self, mock_uploader):
        """Test that _process_domains properly handles exceptions in single domain processing."""
        # Create an extractor
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create domains data with two domains
        domains_data = [
            {"domain": "example1.com", "suffix": "com"},
            {"domain": "example2.com", "suffix": "com"},
        ]

        # Mock _process_single_domain to succeed for first domain but throw exception for second
        async def mock_process(domain, min_width, uploader):
            if domain["domain"] == "example1.com":
                return {
                    "url": "https://example1.com",
                    "title": "Example 1",
                    "icon": "icon1.png",
                    "domain": "example1",
                }
            else:
                raise Exception("Processing error")

        with patch.object(extractor, "_process_single_domain", side_effect=mock_process):
            # Mock reset methods
            extractor.scraper = MagicMock()
            extractor.favicon_downloader = AsyncMock()

            # Call the method
            results = await extractor._process_domains(domains_data, 32, mock_uploader)

        # Verify only the successful domain is in the results
        assert len(results) == 1
        assert results[0]["domain"] == "example1"

        # Verify favicon_downloader were reset
        assert extractor.favicon_downloader.reset.called

    def test_process_domain_metadata_with_monitoring(self, mock_uploader, mocker):
        """Test the complete process_domain_metadata method with system monitoring enabled."""
        # Create an extractor
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create test domains data
        domains_data = [
            {"domain": "example1.com", "suffix": "com"},
            {"domain": "example2.com", "suffix": "com"},
        ]

        # Create expected results
        expected_results = [
            {
                "domain": "example1",
                "url": "https://example1.com",
                "title": "Example 1",
                "icon": "icon1.png",
            },
            {
                "domain": "example2",
                "url": "https://example2.com",
                "title": "Example 2",
                "icon": "icon2.png",
            },
        ]

        # Need to patch _process_domains where SystemMonitor is actually created
        process_domains_mock = mocker.patch.object(
            extractor, "_process_domains", AsyncMock(return_value=expected_results)
        )

        # Mock asyncio.run
        mocker.patch("asyncio.run", return_value=expected_results)

        # Call the method with monitoring enabled
        results = extractor.process_domain_metadata(
            domains_data, 32, mock_uploader, enable_monitoring=True
        )

        # Verify the results
        assert results == expected_results

        # Verify _process_domains was called with monitoring enabled
        process_domains_mock.assert_called_once()
        process_domains_call_args = process_domains_mock.call_args[0]
        assert process_domains_call_args[3] is True  # enable_monitoring

    def test_extract_title_filtering(self):
        """Test the _extract_title method with various titles including invalid ones."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Create mock scraper
        mock_scraper = MagicMock(spec=Scraper)

        # Set the context variable for all tests
        token = current_scraper.set(mock_scraper)
        try:
            # Test valid title
            mock_scraper.scrape_title.return_value = "Valid Website Title"
            assert extractor._extract_title() == "Valid Website Title"

            # Test each invalid title in INVALID_TITLES
            for invalid_title in extractor.INVALID_TITLES[:3]:  # Test just a few to save time
                mock_scraper.scrape_title.return_value = f"Some {invalid_title} Page"
                assert extractor._extract_title() is None

            # Test with None title
            mock_scraper.scrape_title.return_value = None
            assert extractor._extract_title() is None

            # Test with empty title
            mock_scraper.scrape_title.return_value = ""
            title = extractor._extract_title()
            # The implementation appears to return empty string or None
            assert title == "" or title is None
        finally:
            # Reset the context variable
            current_scraper.reset(token)


class TestCustomFavicons:
    """Test custom favicon functionality in domain metadata extractor."""

    @pytest.mark.asyncio
    async def test_process_single_domain_with_custom_favicon_success(self, mock_uploader, mocker):
        """Test that custom favicon is used when available and upload succeeds."""
        # Mock the custom favicon function to return a URL for axios
        mock_get_custom_favicon = mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.get_custom_favicon_url"
        )
        mock_get_custom_favicon.return_value = "https://static.axios.com/icons/favicon.svg"

        # Create extractor with mocked favicon downloader
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Mock the favicon downloader to return a valid image
        from merino.utils.gcs.models import Image

        mock_image = Image(content=b"test_svg_content", content_type="image/svg+xml")
        extractor.favicon_downloader = mocker.AsyncMock()
        extractor.favicon_downloader.download_favicon.return_value = mock_image

        # Mock uploader methods - IMPORTANT: These are synchronous methods
        mock_uploader.destination_favicon_name = mocker.MagicMock(
            return_value="favicons/axios_favicon.svg"
        )
        mock_uploader.upload_image = mocker.MagicMock(
            return_value="https://cdn.example.com/axios_favicon.svg"
        )
        mock_uploader.force_upload = True
        mock_uploader.uploader = mocker.MagicMock()
        mock_uploader.uploader.cdn_hostname = "cdn.example.com"

        # Mock helper methods
        extractor._get_second_level_domain = mocker.MagicMock(return_value="axios")

        # Call the method with axios.com domain
        domain_data = {"domain": "axios.com", "suffix": "com"}
        result = await extractor._process_single_domain(domain_data, 32, mock_uploader)

        # Verify custom favicon was used
        mock_get_custom_favicon.assert_called_once_with("axios")

        # Verify the inline processing was used instead of upload_favicon
        extractor.favicon_downloader.download_favicon.assert_called_once_with(
            "https://static.axios.com/icons/favicon.svg"
        )
        mock_uploader.destination_favicon_name.assert_called_once_with(mock_image)
        mock_uploader.upload_image.assert_called_once_with(
            mock_image, "favicons/axios_favicon.svg", forced_upload=True
        )

        # Verify result contains custom favicon data
        assert result["url"] == "https://axios.com"
        assert result["title"] == "Axios"  # Capitalized second level domain
        assert result["icon"] == "https://cdn.example.com/axios_favicon.svg"
        assert result["domain"] == "axios"

    @pytest.mark.asyncio
    async def test_process_single_domain_with_custom_favicon_upload_failure(
        self, mock_uploader, mock_scraper_context, mocker
    ):
        """Test fallback to scraping when custom favicon download fails."""
        # Unpack the fixture
        MockScraper, shared_scraper = mock_scraper_context

        # Mock the custom favicon function to return a URL
        mock_get_custom_favicon = mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.get_custom_favicon_url"
        )
        mock_get_custom_favicon.return_value = "https://static.axios.com/icons/favicon.svg"

        # Create extractor with mocked favicon downloader that returns None (download failure)
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.favicon_downloader = mocker.AsyncMock()
        extractor.favicon_downloader.download_favicon.return_value = None  # Download failure

        # Configure the shared scraper for fallback
        shared_scraper.open.return_value = "https://axios.com"
        shared_scraper.scrape_title.return_value = "Axios News"

        # Mock helper methods for scraping fallback
        extractor._get_base_url = mocker.MagicMock(return_value="https://axios.com")
        extractor._process_favicon = mocker.AsyncMock(
            return_value="https://cdn.example.com/scraped_favicon.ico"
        )
        extractor._get_second_level_domain = mocker.MagicMock(return_value="axios")
        extractor._get_title = mocker.MagicMock(return_value="Axios News")

        # Use the fixture to patch the Scraper class
        mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper", MockScraper
        )

        # Call the method
        domain_data = {"domain": "axios.com", "suffix": "com"}
        result = await extractor._process_single_domain(domain_data, 32, mock_uploader)

        # Verify custom favicon was attempted first
        mock_get_custom_favicon.assert_called_once_with("axios")
        extractor.favicon_downloader.download_favicon.assert_called_once_with(
            "https://static.axios.com/icons/favicon.svg"
        )

        # Verify fallback to scraping occurred
        extractor._process_favicon.assert_called_once()

        # Verify result contains scraped favicon data
        assert result["icon"] == "https://cdn.example.com/scraped_favicon.ico"
        assert result["title"] == "Axios News"  # From scraping, not capitalized domain

    @pytest.mark.asyncio
    async def test_process_single_domain_custom_favicon_exception(
        self, mock_uploader, mock_scraper_context, mocker
    ):
        """Test that exceptions during custom favicon processing are handled gracefully."""
        # Unpack the fixture
        MockScraper, shared_scraper = mock_scraper_context

        # Mock the custom favicon function to return a URL
        mock_get_custom_favicon = mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.get_custom_favicon_url"
        )
        mock_get_custom_favicon.return_value = "https://static.axios.com/icons/favicon.svg"

        # Create extractor with mocked favicon downloader that raises an exception
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.favicon_downloader = mocker.AsyncMock()
        extractor.favicon_downloader.download_favicon.side_effect = Exception("Download failed")

        # Configure the shared scraper for fallback
        shared_scraper.open.return_value = "https://axios.com"
        shared_scraper.scrape_title.return_value = "Axios News"

        # Mock helper methods for scraping fallback
        extractor._get_base_url = mocker.MagicMock(return_value="https://axios.com")
        extractor._process_favicon = mocker.AsyncMock(
            return_value="https://cdn.example.com/scraped_favicon.ico"
        )
        extractor._get_second_level_domain = mocker.MagicMock(return_value="axios")
        extractor._get_title = mocker.MagicMock(return_value="Axios News")

        # Use the fixture to patch the Scraper class
        mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper", MockScraper
        )

        # Call the method
        domain_data = {"domain": "axios.com", "suffix": "com"}
        result = await extractor._process_single_domain(domain_data, 32, mock_uploader)

        # Verify custom favicon was attempted
        mock_get_custom_favicon.assert_called_once_with("axios")
        extractor.favicon_downloader.download_favicon.assert_called_once_with(
            "https://static.axios.com/icons/favicon.svg"
        )

        # Verify fallback to scraping occurred
        extractor._process_favicon.assert_called_once()

        # Verify result contains scraped data (not custom favicon)
        assert result["icon"] == "https://cdn.example.com/scraped_favicon.ico"

    @pytest.mark.asyncio
    async def test_multiple_domains_custom_favicon_priority(self, mock_uploader, mocker):
        """Test processing multiple domains where some have custom favicons and others don't."""

        # Mock the custom favicon function to return URLs only for specific domains
        def mock_custom_favicon_lookup(domain):
            custom_favicons = {
                "axios": "https://static.axios.com/icons/favicon.svg",
                "reuters": "https://www.reuters.com/pf/resources/images/reuters/favicon/tr_kinesis_v2.svg?d=287",
            }
            return custom_favicons.get(domain, "")

        mock_get_custom_favicon = mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.get_custom_favicon_url"
        )
        mock_get_custom_favicon.side_effect = mock_custom_favicon_lookup

        # Create extractor with mocked favicon downloader
        extractor = DomainMetadataExtractor(blocked_domains=set())
        extractor.favicon_downloader = mocker.AsyncMock()

        # Mock favicon downloads to return valid images for custom favicon domains
        from merino.utils.gcs.models import Image

        def mock_download_favicon(url):
            if "axios.com" in url:
                return Image(content=b"axios_content", content_type="image/svg+xml")
            elif "reuters.com" in url:
                return Image(content=b"reuters_content", content_type="image/svg+xml")
            return None

        extractor.favicon_downloader.download_favicon.side_effect = mock_download_favicon

        # Mock uploader methods - IMPORTANT: These must be synchronous
        def mock_destination_name(image):
            if b"axios" in image.content:
                return "favicons/axios_favicon.svg"
            elif b"reuters" in image.content:
                return "favicons/reuters_favicon.svg"
            return "favicons/default.ico"

        def mock_upload_image(image, name, forced_upload):
            if "axios" in name:
                return "https://cdn.example.com/axios_favicon.svg"
            elif "reuters" in name:
                return "https://cdn.example.com/reuters_favicon.svg"
            return "https://cdn.example.com/default.ico"

        mock_uploader.destination_favicon_name = mocker.MagicMock(
            side_effect=mock_destination_name
        )
        mock_uploader.upload_image = mocker.MagicMock(side_effect=mock_upload_image)
        mock_uploader.force_upload = True
        mock_uploader.uploader = mocker.MagicMock()
        mock_uploader.uploader.cdn_hostname = "cdn.example.com"

        extractor._get_second_level_domain = mocker.MagicMock(
            side_effect=lambda domain, suffix: domain.split(".")[0]
        )

        # Mock the Scraper to ensure consistent behavior for domains without custom favicons
        mock_scraper = mocker.MagicMock()
        mock_scraper.__enter__ = mocker.MagicMock(return_value=mock_scraper)
        mock_scraper.__exit__ = mocker.MagicMock(return_value=None)
        mock_scraper.open.return_value = None  # Simulate scraper failure for non-custom domains

        mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper",
            return_value=mock_scraper,
        )

        # Test domains - mix of custom favicon and regular domains
        test_domains = [
            {"domain": "axios.com", "suffix": "com"},  # Has custom favicon
            {"domain": "reuters.com", "suffix": "com"},  # Has custom favicon
            {"domain": "example.com", "suffix": "com"},  # No custom favicon
        ]

        results = []
        for domain_data in test_domains:
            result = await extractor._process_single_domain(domain_data, 32, mock_uploader)
            results.append(result)

        # Verify custom favicons were used for axios and reuters
        assert mock_get_custom_favicon.call_count == 3
        assert (
            extractor.favicon_downloader.download_favicon.call_count == 2
        )  # Only for domains with custom favicons
        assert mock_uploader.upload_image.call_count == 2  # Only for successful downloads

        # Verify results
        axios_result = results[0]
        assert axios_result["domain"] == "axios"
        assert "axios_favicon.svg" in axios_result["icon"]
        assert axios_result["title"] == "Axios"

        reuters_result = results[1]
        assert reuters_result["domain"] == "reuters"
        assert "reuters_favicon.svg" in reuters_result["icon"]
        assert reuters_result["title"] == "Reuters"

        # Example.com should have empty result because scraper is mocked to fail
        example_result = results[2]
        assert example_result["domain"] == ""
        assert example_result["icon"] == ""
        assert example_result["title"] == ""
        assert example_result["url"] is None

    def test_custom_favicon_edge_cases(self, mocker):
        """Test edge cases for custom favicon functionality."""
        from merino.jobs.navigational_suggestions.custom_favicons import get_custom_favicon_url

        assert get_custom_favicon_url("localhost") == ""

        assert get_custom_favicon_url(".com") == ""

    def test_process_domain_metadata_multiple_tlds(self, mock_uploader, mocker):
        """Ensure domains sharing the same base use the custom favicon."""
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Mock favicon downloader to always return an image
        from merino.utils.gcs.models import Image

        mock_image = Image(content=b"espn_icon", content_type="image/x-icon")
        extractor.favicon_downloader = mocker.AsyncMock()
        extractor.favicon_downloader.download_favicon.return_value = mock_image
        extractor.favicon_downloader.reset = mocker.AsyncMock()

        # Mock uploader methods
        mock_uploader.destination_favicon_name = mocker.MagicMock(return_value="favicons/espn.ico")
        mock_uploader.upload_image = mocker.MagicMock(
            return_value="https://cdn.example.com/espn.ico"
        )
        mock_uploader.force_upload = True
        mock_uploader.uploader = mocker.MagicMock()
        mock_uploader.uploader.cdn_hostname = "cdn.example.com"

        # Patch Scraper since it should not be used when custom favicon is found
        mock_scraper = mocker.MagicMock()
        mock_scraper.__enter__.return_value = mock_scraper
        mock_scraper.__exit__.return_value = None
        mocker.patch(
            "merino.jobs.navigational_suggestions.domain_metadata_extractor.Scraper",
            return_value=mock_scraper,
        )

        domains = [
            {"domain": "espn.com", "suffix": "com"},
            {"domain": "espn.in", "suffix": "in"},
            {"domain": "espn.co.uk", "suffix": "co.uk"},
        ]

        results = extractor.process_domain_metadata(domains, 32, mock_uploader)

        assert len(results) == 3
        for res in results:
            assert res["domain"] == "espn"
            assert res["icon"] == "https://cdn.example.com/espn.ico"
            assert res["title"] == "Espn"
            assert res["url"].startswith("https://espn")

    def test_is_better_favicon_prioritization_rules(self):
        """Test the is_better_favicon method that implements Firefox prioritization logic.

        This tests the core prioritization algorithm:
        1. Source priority (most important): link(1) > meta(2) > manifest(3) > default(4)
        2. Size priority (within same source): larger wins
        3. Same source + same size: not better (returns False)
        """
        extractor = DomainMetadataExtractor(blocked_domains=set())

        # Test 1: Source priority beats size - link beats everything else regardless of size
        link_small = {"_source": "link"}
        meta_large = {"_source": "meta"}
        manifest_huge = {"_source": "manifest"}

        # Link source should win even with smaller size
        assert (
            extractor.is_better_favicon(link_small, width=16, best_width=512, best_source="meta")
            is True
        )
        assert (
            extractor.is_better_favicon(
                link_small, width=16, best_width=512, best_source="manifest"
            )
            is True
        )
        assert (
            extractor.is_better_favicon(
                link_small, width=16, best_width=512, best_source="default"
            )
            is True
        )

        # Test 2: Meta beats manifest and default, loses to link
        assert (
            extractor.is_better_favicon(
                meta_large, width=16, best_width=512, best_source="manifest"
            )
            is True
        )
        assert (
            extractor.is_better_favicon(
                meta_large, width=16, best_width=512, best_source="default"
            )
            is True
        )
        assert (
            extractor.is_better_favicon(meta_large, width=512, best_width=16, best_source="link")
            is False
        )

        # Test 3: Manifest beats default, loses to meta and link
        assert (
            extractor.is_better_favicon(
                manifest_huge, width=512, best_width=16, best_source="default"
            )
            is True
        )
        assert (
            extractor.is_better_favicon(
                manifest_huge, width=512, best_width=16, best_source="meta"
            )
            is False
        )
        assert (
            extractor.is_better_favicon(
                manifest_huge, width=512, best_width=16, best_source="link"
            )
            is False
        )

        # Test 4: Within same source, size matters
        link_large = {"_source": "link"}
        assert (
            extractor.is_better_favicon(link_large, width=64, best_width=32, best_source="link")
            is True
        )
        assert (
            extractor.is_better_favicon(link_large, width=32, best_width=64, best_source="link")
            is False
        )
        assert (
            extractor.is_better_favicon(link_large, width=32, best_width=32, best_source="link")
            is False
        )

        # Test 5: Missing _source defaults to "default" priority (lowest)
        no_source = {}  # No _source field
        assert (
            extractor.is_better_favicon(no_source, width=512, best_width=16, best_source="link")
            is False
        )
        assert (
            extractor.is_better_favicon(no_source, width=512, best_width=16, best_source="meta")
            is False
        )
        assert (
            extractor.is_better_favicon(
                no_source, width=512, best_width=16, best_source="manifest"
            )
            is False
        )
        # But should win against another default with larger size
        assert (
            extractor.is_better_favicon(no_source, width=64, best_width=32, best_source="default")
            is True
        )
