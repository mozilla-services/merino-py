# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for web_scraper module."""

import pytest
from bs4 import BeautifulSoup

from merino.jobs.navigational_suggestions.scrapers.web_scraper import WebScraper


class TestWebScraperContextManager:
    """Tests for WebScraper context manager functionality."""

    def test_context_manager_enter_exit(self, mocker):
        """Test that WebScraper works as a context manager."""
        mock_close = mocker.patch.object(WebScraper, "close")

        with WebScraper() as scraper:
            assert scraper is not None
            assert hasattr(scraper, "browser")

        mock_close.assert_called_once()

    def test_context_manager_exit_on_exception(self, mocker):
        """Test that close is called even when exception occurs."""
        mock_close = mocker.patch.object(WebScraper, "close")

        with pytest.raises(ValueError):
            with WebScraper():
                raise ValueError("Test exception")

        mock_close.assert_called_once()


class TestWebScraperOpen:
    """Tests for WebScraper.open method."""

    def test_open_successful(self, mocker):
        """Test successful URL opening."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.url = "https://example.com"
        scraper.browser = mock_browser

        result = scraper.open("https://example.com")

        assert result == "https://example.com"
        mock_browser.open.assert_called_once_with(
            "https://example.com", timeout=mocker.ANY, allow_redirects=mocker.ANY
        )

    def test_open_with_redirect(self, mocker):
        """Test opening URL that redirects."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.url = "https://www.example.com/redirected"
        scraper.browser = mock_browser

        result = scraper.open("https://example.com")

        assert result == "https://www.example.com/redirected"

    def test_open_failure_returns_none(self, mocker):
        """Test that open returns None on failure."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.open.side_effect = Exception("Connection failed")
        scraper.browser = mock_browser

        result = scraper.open("https://example.com")

        assert result is None

    def test_open_timeout_returns_none(self, mocker):
        """Test that open returns None on timeout."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.open.side_effect = TimeoutError("Request timed out")
        scraper.browser = mock_browser

        result = scraper.open("https://example.com")

        assert result is None


class TestWebScraperScrapeTitle:
    """Tests for WebScraper.scrape_title method."""

    def test_scrape_title_success(self, mocker):
        """Test successful title extraction."""
        html = "<html><head><title>Example Title</title></head></html>"
        soup = BeautifulSoup(html, "html.parser")

        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = soup
        scraper.browser = mock_browser

        result = scraper.scrape_title()

        assert result == "Example Title"

    def test_scrape_title_with_whitespace(self, mocker):
        """Test title extraction with whitespace."""
        html = "<html><head><title>  Title with Spaces  </title></head></html>"
        soup = BeautifulSoup(html, "html.parser")

        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = soup
        scraper.browser = mock_browser

        result = scraper.scrape_title()

        assert result == "  Title with Spaces  "

    def test_scrape_title_missing_returns_none(self, mocker):
        """Test that missing title returns None."""
        html = "<html><head></head></html>"
        soup = BeautifulSoup(html, "html.parser")

        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = soup
        scraper.browser = mock_browser

        result = scraper.scrape_title()

        assert result is None

    def test_scrape_title_no_head_returns_none(self, mocker):
        """Test that missing head tag returns None."""
        html = "<html><body>No head</body></html>"
        soup = BeautifulSoup(html, "html.parser")

        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = soup
        scraper.browser = mock_browser

        result = scraper.scrape_title()

        assert result is None

    def test_scrape_title_exception_returns_none(self, mocker):
        """Test that exception during scraping returns None."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page.find.side_effect = Exception("Parse error")
        scraper.browser = mock_browser

        result = scraper.scrape_title()

        assert result is None


class TestWebScraperGetPage:
    """Tests for WebScraper.get_page method."""

    def test_get_page_returns_soup(self, mocker):
        """Test that get_page returns BeautifulSoup object."""
        html = "<html><body>Test</body></html>"
        soup = BeautifulSoup(html, "html.parser")

        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = soup
        scraper.browser = mock_browser

        result = scraper.get_page()

        assert result is soup
        assert isinstance(result, BeautifulSoup)

    def test_get_page_returns_none_when_no_page(self, mocker):
        """Test that get_page returns None when no page loaded."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.page = None
        scraper.browser = mock_browser

        result = scraper.get_page()

        assert result is None


class TestWebScraperGetCurrentUrl:
    """Tests for WebScraper.get_current_url method."""

    def test_get_current_url_success(self, mocker):
        """Test getting current URL."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.url = "https://example.com/current"
        scraper.browser = mock_browser

        result = scraper.get_current_url()

        assert result == "https://example.com/current"

    def test_get_current_url_none_when_no_url(self, mocker):
        """Test that None is returned when no URL."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.url = None
        scraper.browser = mock_browser

        result = scraper.get_current_url()

        assert result is None

    def test_get_current_url_exception_returns_none(self, mocker):
        """Test that exception returns None."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        # Create a property that raises an exception when accessed
        type(mock_browser).url = mocker.PropertyMock(side_effect=Exception("Error"))
        scraper.browser = mock_browser

        result = scraper.get_current_url()

        assert result is None


class TestWebScraperClose:
    """Tests for WebScraper.close method."""

    def test_close_closes_session(self, mocker):
        """Test that close properly closes the session."""
        scraper = WebScraper()
        mock_session = mocker.MagicMock()
        scraper.browser.session = mock_session

        scraper.close()

        mock_session.close.assert_called_once()

    def test_close_calls_browser_close(self, mocker):
        """Test that browser.close is called."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        scraper.browser = mock_browser

        scraper.close()

        mock_browser.close.assert_called_once()

    def test_close_handles_exception(self, mocker, caplog):
        """Test that close handles exceptions gracefully."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser.session.close.side_effect = Exception("Close failed")
        scraper.browser = mock_browser

        # Should not raise exception
        scraper.close()

        assert "Error occurred when closing scraper session" in caplog.text

    def test_close_cleans_up_browser_reference(self, mocker):
        """Test that _browser reference is cleaned up."""
        scraper = WebScraper()
        mock_browser = mocker.MagicMock()
        mock_browser._browser = "something"
        scraper.browser = mock_browser

        scraper.close()

        assert scraper.browser._browser is None
