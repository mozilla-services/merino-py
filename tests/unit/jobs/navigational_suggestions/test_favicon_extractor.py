"""Complete test coverage for favicon_extractor.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bs4 import BeautifulSoup

from merino.jobs.navigational_suggestions.favicon.favicon_extractor import FaviconExtractor
from merino.jobs.navigational_suggestions.models import FaviconData
from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import FaviconScraper


@pytest.fixture
def mock_favicon_scraper():
    """Mock favicon scraper for testing."""
    scraper = MagicMock(spec=FaviconScraper)
    return scraper


@pytest.fixture
def favicon_extractor(mock_favicon_scraper):
    """Create FaviconExtractor instance with mocked dependencies."""
    return FaviconExtractor(mock_favicon_scraper)


@pytest.fixture
def sample_page():
    """Create a sample BeautifulSoup page."""
    html = """
    <html>
        <head>
            <link rel="icon" href="/favicon.ico">
            <meta name="apple-touch-icon" content="/apple-touch.png">
        </head>
    </html>
    """
    return BeautifulSoup(html, "html.parser")


class TestFaviconExtractorInit:
    """Test FaviconExtractor initialization."""

    def test_init_with_favicon_scraper(self, mock_favicon_scraper):
        """Test initialization with favicon scraper."""
        extractor = FaviconExtractor(mock_favicon_scraper)
        assert extractor.favicon_scraper == mock_favicon_scraper


class TestExtractFavicons:
    """Test the main extract_favicons method."""

    @pytest.mark.asyncio
    async def test_extract_favicons_full_flow(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test full favicon extraction flow with all types."""
        # Mock favicon data
        favicon_data = FaviconData(
            links=[{"href": "/favicon.ico", "rel": ["icon"]}],
            metas=[{"content": "/apple-touch.png", "name": "apple-touch-icon"}],
            manifests=[{"href": "/manifest.json"}],
        )
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data

        # Mock default favicon
        mock_favicon_scraper.get_default_favicon = AsyncMock(
            return_value="https://example.com/favicon.ico"
        )

        # Mock manifest scraping
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": "/icon-192.png", "sizes": "192x192"}]
        )

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=10
        )

        # Should have processed links, metas, default, and manifest
        assert len(result) >= 3
        assert any("favicon.ico" in str(favicon.get("href", "")) for favicon in result)

        # Verify scraper was called
        mock_favicon_scraper.scrape_favicon_data.assert_called_once_with(sample_page)

    @pytest.mark.asyncio
    async def test_extract_favicons_early_stopping_after_links(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test early stopping when max_icons reached after processing links."""
        # Create enough links to hit max_icons limit
        links = [{"href": f"/icon{i}.png", "rel": ["icon"]} for i in range(5)]
        favicon_data = FaviconData(links=links, metas=[], manifests=[])
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=3
        )

        # Should stop at max_icons and not process metas/default/manifest
        assert len(result) == 3
        assert all(favicon["_source"] == "link" for favicon in result)

    @pytest.mark.asyncio
    async def test_extract_favicons_early_stopping_after_metas(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test early stopping when max_icons reached after processing metas."""
        favicon_data = FaviconData(
            links=[{"href": "/favicon.ico", "rel": ["icon"]}],
            metas=[{"content": f"/meta{i}.png"} for i in range(3)],
            manifests=[],
        )
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=3
        )

        # Should stop at max_icons
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_extract_favicons_with_none_page(self, favicon_extractor, mock_favicon_scraper):
        """Test extract_favicons with None page."""
        favicon_data = FaviconData(links=[], metas=[], manifests=[])
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data
        mock_favicon_scraper.get_default_favicon = AsyncMock(return_value=None)

        result = await favicon_extractor.extract_favicons(None, "https://example.com")

        assert result == []
        mock_favicon_scraper.scrape_favicon_data.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_extract_favicons_exception_handling(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test exception handling in extract_favicons."""
        mock_favicon_scraper.scrape_favicon_data.side_effect = Exception("Scraping failed")

        result = await favicon_extractor.extract_favicons(sample_page, "https://example.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_favicons_with_manifest_processing(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test favicon extraction that includes manifest processing."""
        favicon_data = FaviconData(links=[], metas=[], manifests=[{"href": "/manifest.json"}])
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data
        mock_favicon_scraper.get_default_favicon = AsyncMock(return_value=None)
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": "/icon-192.png"}]
        )

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=5
        )

        assert len(result) == 1
        assert result[0]["_source"] == "manifest"


class TestProcessLinkFavicons:
    """Test _process_link_favicons method."""

    def test_process_link_favicons_basic(self, favicon_extractor):
        """Test basic link favicon processing."""
        links = [
            {"href": "/favicon.ico", "rel": ["icon"]},
            {"href": "/apple-touch.png", "rel": ["apple-touch-icon"]},
        ]

        result = favicon_extractor._process_link_favicons(links, "https://example.com", 5)

        assert len(result) == 2
        assert all(favicon["_source"] == "link" for favicon in result)
        assert result[0]["href"] == "https://example.com/favicon.ico"

    def test_process_link_favicons_with_problematic_urls(self, favicon_extractor):
        """Test link favicon processing that skips problematic URLs."""
        links = [
            {"href": "data:image/png;base64,abc123", "rel": ["icon"]},  # Should be skipped
            {"href": "/favicon.ico", "rel": ["icon"]},  # Should be processed
        ]

        with patch(
            "merino.jobs.navigational_suggestions.utils.process_favicon_url"
        ) as mock_process:
            mock_process.side_effect = [
                None,
                {"href": "https://example.com/favicon.ico", "_source": "link"},
            ]

            result = favicon_extractor._process_link_favicons(links, "https://example.com", 5)

        assert len(result) == 1
        assert result[0]["href"] == "https://example.com/favicon.ico"

    def test_process_link_favicons_early_stopping(self, favicon_extractor):
        """Test early stopping in link processing."""
        links = [{"href": f"/icon{i}.png", "rel": ["icon"]} for i in range(10)]

        result = favicon_extractor._process_link_favicons(links, "https://example.com", 3)

        assert len(result) == 3

    def test_process_link_favicons_empty_list(self, favicon_extractor):
        """Test processing empty link list."""
        result = favicon_extractor._process_link_favicons([], "https://example.com", 5)
        assert result == []

    def test_process_link_favicons_preserves_attributes(self, favicon_extractor):
        """Test that link processing preserves original attributes."""
        links = [{"href": "/favicon.ico", "rel": ["icon"], "sizes": "32x32", "type": "image/png"}]

        result = favicon_extractor._process_link_favicons(links, "https://example.com", 5)

        assert len(result) == 1
        assert result[0]["sizes"] == "32x32"
        assert result[0]["type"] == "image/png"
        assert result[0]["rel"] == ["icon"]


class TestProcessMetaFavicons:
    """Test _process_meta_favicons method."""

    def test_process_meta_favicons_basic(self, favicon_extractor):
        """Test basic meta favicon processing."""
        metas = [
            {"content": "/apple-touch.png", "name": "apple-touch-icon"},
            {"content": "https://example.com/tile.png", "name": "msapplication-TileImage"},
        ]

        result = favicon_extractor._process_meta_favicons(metas, "https://example.com", 5)

        assert len(result) == 2
        assert all(favicon["_source"] == "meta" for favicon in result)
        assert result[0]["href"] == "https://example.com/apple-touch.png"
        assert result[1]["href"] == "https://example.com/tile.png"

    def test_process_meta_favicons_with_absolute_urls(self, favicon_extractor):
        """Test meta processing with absolute URLs."""
        metas = [{"content": "https://cdn.example.com/icon.png", "name": "apple-touch-icon"}]

        result = favicon_extractor._process_meta_favicons(metas, "https://example.com", 5)

        assert len(result) == 1
        assert result[0]["href"] == "https://cdn.example.com/icon.png"

    def test_process_meta_favicons_early_stopping(self, favicon_extractor):
        """Test early stopping in meta processing."""
        metas = [{"content": f"/meta{i}.png"} for i in range(10)]

        result = favicon_extractor._process_meta_favicons(metas, "https://example.com", 3)

        assert len(result) == 3

    def test_process_meta_favicons_with_problematic_urls(self, favicon_extractor):
        """Test meta processing that skips problematic URLs."""
        metas = [
            {"content": "data:image/png;base64,abc123"},  # Should be skipped
            {"content": "/apple-touch.png"},  # Should be processed
        ]

        with patch(
            "merino.jobs.navigational_suggestions.utils.process_favicon_url"
        ) as mock_process:
            mock_process.side_effect = [
                None,
                {"href": "https://example.com/apple-touch.png", "_source": "meta"},
            ]

            result = favicon_extractor._process_meta_favicons(metas, "https://example.com", 5)

        assert len(result) == 1

    def test_process_meta_favicons_preserves_attributes(self, favicon_extractor):
        """Test that meta processing preserves original attributes."""
        metas = [{"content": "/apple-touch.png", "name": "apple-touch-icon", "sizes": "180x180"}]

        result = favicon_extractor._process_meta_favicons(metas, "https://example.com", 5)

        assert len(result) == 1
        assert result[0]["name"] == "apple-touch-icon"
        assert result[0]["sizes"] == "180x180"


class TestProcessDefaultFavicon:
    """Test _process_default_favicon method."""

    @pytest.mark.asyncio
    async def test_process_default_favicon_success(self, favicon_extractor, mock_favicon_scraper):
        """Test successful default favicon processing."""
        mock_favicon_scraper.get_default_favicon = AsyncMock(
            return_value="https://example.com/favicon.ico"
        )

        result = await favicon_extractor._process_default_favicon("https://example.com")

        assert result == {"href": "https://example.com/favicon.ico", "_source": "default"}

    @pytest.mark.asyncio
    async def test_process_default_favicon_not_found(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test default favicon processing when not found."""
        mock_favicon_scraper.get_default_favicon = AsyncMock(return_value=None)

        result = await favicon_extractor._process_default_favicon("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_process_default_favicon_exception(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test default favicon processing with exception."""
        mock_favicon_scraper.get_default_favicon = AsyncMock(
            side_effect=Exception("Network error")
        )

        result = await favicon_extractor._process_default_favicon("https://example.com")

        assert result is None


class TestProcessManifestFavicons:
    """Test _process_manifest_favicons method."""

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_success(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test successful manifest favicon processing."""
        manifests = [{"href": "/manifest.json"}]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[
                {"src": "/icon-192.png", "sizes": "192x192"},
                {"src": "/icon-512.png", "sizes": "512x512"},
            ]
        )

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 5
        )

        assert len(result) == 2
        assert all(favicon["_source"] == "manifest" for favicon in result)
        assert result[0]["href"] == "https://example.com/icon-192.png"

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_with_absolute_urls(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test manifest processing with absolute URLs in src."""
        manifests = [{"href": "/manifest.json"}]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": "https://cdn.example.com/icon.png"}]
        )

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 5
        )

        assert len(result) == 1
        assert result[0]["href"] == "https://cdn.example.com/icon.png"

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_early_stopping(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test early stopping in manifest processing."""
        manifests = [{"href": "/manifest.json"}]
        icons = [{"src": f"/icon-{i}.png"} for i in range(10)]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(return_value=icons)

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 3
        )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_with_problematic_urls(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test manifest processing that skips problematic URLs."""
        manifests = [{"href": "/manifest.json"}]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[
                {"src": "data:image/png;base64,abc123"},  # Should be skipped
                {"src": "/icon.png"},  # Should be processed
            ]
        )

        with patch(
            "merino.jobs.navigational_suggestions.utils.is_problematic_favicon_url"
        ) as mock_check:
            mock_check.side_effect = [True, False]

            result = await favicon_extractor._process_manifest_favicons(
                manifests, "https://example.com", 5
            )

        assert len(result) == 1
        assert "icon.png" in result[0]["href"]

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_empty_list(self, favicon_extractor):
        """Test processing empty manifest list."""
        result = await favicon_extractor._process_manifest_favicons([], "https://example.com", 5)
        assert result == []

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_no_href(self, favicon_extractor):
        """Test processing manifest without href."""
        manifests = [{"rel": "manifest"}]  # Missing href

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 5
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_exception(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test manifest processing with exception."""
        manifests = [{"href": "/manifest.json"}]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            side_effect=Exception("Parse error")
        )

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 5
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_process_manifest_favicons_only_first_manifest(
        self, favicon_extractor, mock_favicon_scraper
    ):
        """Test that only the first manifest is processed."""
        manifests = [{"href": "/manifest1.json"}, {"href": "/manifest2.json"}]
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": "/icon.png"}]
        )

        result = await favicon_extractor._process_manifest_favicons(
            manifests, "https://example.com", 5
        )

        # Should only call with first manifest
        mock_favicon_scraper.scrape_favicons_from_manifest.assert_called_once()
        call_args = mock_favicon_scraper.scrape_favicons_from_manifest.call_args[0]
        assert "manifest1.json" in call_args[0]

        # Verify result contains processed favicon
        assert len(result) == 1
        assert result[0]["href"] == "https://example.com/icon.png"


class TestIntegrationScenarios:
    """Test various integration scenarios."""

    @pytest.mark.asyncio
    async def test_extract_favicons_mixed_sources_priority(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test that sources are processed in correct priority order."""
        favicon_data = FaviconData(
            links=[{"href": "/favicon.ico", "rel": ["icon"]}],
            metas=[{"content": "/apple-touch.png"}],
            manifests=[{"href": "/manifest.json"}],
        )
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data
        mock_favicon_scraper.get_default_favicon = AsyncMock(
            return_value="https://example.com/favicon.ico"
        )
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": "/icon-192.png"}]
        )

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=10
        )

        # Check that sources are in expected order
        sources = [favicon["_source"] for favicon in result]
        link_index = next((i for i, s in enumerate(sources) if s == "link"), -1)
        meta_index = next((i for i, s in enumerate(sources) if s == "meta"), -1)
        default_index = next((i for i, s in enumerate(sources) if s == "default"), -1)
        manifest_index = next((i for i, s in enumerate(sources) if s == "manifest"), -1)

        # Links should come before metas, metas before default, default before manifest
        assert link_index < meta_index < default_index < manifest_index

    @pytest.mark.asyncio
    async def test_extract_favicons_max_icons_respected_across_all_phases(
        self, favicon_extractor, sample_page, mock_favicon_scraper
    ):
        """Test that max_icons is respected across all processing phases."""
        favicon_data = FaviconData(
            links=[{"href": f"/link{i}.ico", "rel": ["icon"]} for i in range(2)],
            metas=[{"content": f"/meta{i}.png"} for i in range(2)],
            manifests=[{"href": "/manifest.json"}],
        )
        mock_favicon_scraper.scrape_favicon_data.return_value = favicon_data
        mock_favicon_scraper.get_default_favicon = AsyncMock(
            return_value="https://example.com/favicon.ico"
        )
        mock_favicon_scraper.scrape_favicons_from_manifest = AsyncMock(
            return_value=[{"src": f"/manifest{i}.png"} for i in range(2)]
        )

        result = await favicon_extractor.extract_favicons(
            sample_page, "https://example.com", max_icons=4
        )

        # Should stop at exactly max_icons
        assert len(result) == 4
