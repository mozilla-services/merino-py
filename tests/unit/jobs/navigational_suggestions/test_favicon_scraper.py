# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for favicon_scraper module."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import AsyncMock

from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import FaviconScraper
from merino.jobs.navigational_suggestions.models import FaviconData


class TestFaviconScraperScrapeData:
    """Tests for FaviconScraper.scrape_favicon_data method."""

    def test_scrape_link_tags(self):
        """Test scraping favicon from link tags."""
        html = """
        <html>
            <head>
                <link rel="icon" href="/favicon.ico">
                <link rel="apple-touch-icon" href="/apple-icon.png">
            </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(soup)

        assert isinstance(result, FaviconData)
        assert len(result.links) == 2
        assert result.links[0]["href"] == "/favicon.ico"
        assert result.links[1]["href"] == "/apple-icon.png"

    def test_scrape_meta_tags(self):
        """Test scraping favicon from meta tags."""
        html = """
        <html>
            <head>
                <meta name="apple-touch-icon" content="/apple-icon.png">
                <meta name="msapplication-TileImage" content="/tile-image.png">
            </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(soup)

        assert isinstance(result, FaviconData)
        assert len(result.metas) == 2

    def test_scrape_manifest_links(self):
        """Test scraping manifest links."""
        html = """
        <html>
            <head>
                <link rel="manifest" href="/manifest.json">
            </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(soup)

        assert isinstance(result, FaviconData)
        assert len(result.manifests) == 1
        assert result.manifests[0]["href"] == "/manifest.json"

    def test_scrape_empty_page(self):
        """Test scraping page with no favicon information."""
        html = "<html><head></head><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(soup)

        assert isinstance(result, FaviconData)
        assert len(result.links) == 0
        assert len(result.metas) == 0
        assert len(result.manifests) == 0

    def test_scrape_handles_exception(self, mocker, caplog):
        """Test that scraping handles exceptions gracefully."""
        mock_page = mocker.MagicMock()
        mock_page.select.side_effect = Exception("Parse error")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(mock_page)

        assert isinstance(result, FaviconData)
        assert len(result.links) == 0
        assert len(result.metas) == 0
        assert len(result.manifests) == 0
        assert "Error scraping favicon data" in caplog.text


class TestFaviconScraperManifest:
    """Tests for FaviconScraper.scrape_favicons_from_manifest method."""

    @pytest.mark.asyncio
    async def test_scrape_manifest_success(self, mocker):
        """Test successful manifest scraping."""
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = {
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192"},
                {"src": "/icon-512.png", "sizes": "512x512"},
            ]
        }

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert len(result) == 2
        assert result[0]["src"] == "/icon-192.png"
        assert result[1]["sizes"] == "512x512"

    @pytest.mark.asyncio
    async def test_scrape_manifest_no_icons(self, mocker):
        """Test manifest with no icons array."""
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = {"name": "App"}

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_manifest_invalid_json(self, mocker):
        """Test manifest with invalid JSON."""
        mock_response = mocker.MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_manifest_no_response(self, mocker):
        """Test manifest request returns None."""
        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=None)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_manifest_exception(self, mocker):
        """Test manifest scraping handles exceptions."""
        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(side_effect=Exception("Network error"))

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_manifest_missing_json_method(self, mocker):
        """Test manifest response without json method."""
        mock_response = mocker.MagicMock()
        del mock_response.json

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.scrape_favicons_from_manifest("https://example.com/manifest.json")

        assert result == []


class TestFaviconScraperDefaultFavicon:
    """Tests for FaviconScraper.get_default_favicon method."""

    @pytest.mark.asyncio
    async def test_get_default_favicon_exists(self, mocker):
        """Test getting default favicon when it exists."""
        mock_response = mocker.MagicMock()
        mock_response.url = "https://example.com/favicon.ico"

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.get_default_favicon("https://example.com")

        assert result == "https://example.com/favicon.ico"
        mock_downloader.requests_get.assert_called_once_with("https://example.com/favicon.ico")

    @pytest.mark.asyncio
    async def test_get_default_favicon_not_found(self, mocker):
        """Test getting default favicon when it doesn't exist."""
        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=None)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.get_default_favicon("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_default_favicon_exception(self, mocker):
        """Test default favicon handles exceptions."""
        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(side_effect=Exception("Connection error"))

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.get_default_favicon("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_default_favicon_with_redirect(self, mocker):
        """Test default favicon with redirect."""
        mock_response = mocker.MagicMock()
        mock_response.url = "https://cdn.example.com/icons/favicon.ico"

        mock_downloader = mocker.MagicMock()
        mock_downloader.requests_get = AsyncMock(return_value=mock_response)

        scraper = FaviconScraper(mock_downloader)

        result = await scraper.get_default_favicon("https://example.com")

        assert result == "https://cdn.example.com/icons/favicon.ico"

    @pytest.mark.asyncio
    async def test_get_default_favicon_uses_default_downloader(self):
        """Test that FaviconScraper creates default downloader if none provided."""
        scraper = FaviconScraper()

        assert scraper.async_downloader is not None


class TestFaviconScraperIntegration:
    """Integration tests for FaviconScraper."""

    def test_scrape_complex_page(self):
        """Test scraping page with multiple favicon sources."""
        html = """
        <html>
            <head>
                <link rel="icon" href="/favicon.ico">
                <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
                <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
                <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
                <link rel="manifest" href="/site.webmanifest">
                <meta property="og:image" content="/og-image.png">
            </head>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = FaviconScraper()

        result = scraper.scrape_favicon_data(soup)

        assert len(result.links) >= 4
        assert len(result.manifests) == 1
        # Only specific meta tags are captured by the selector
        assert isinstance(result.metas, list)
