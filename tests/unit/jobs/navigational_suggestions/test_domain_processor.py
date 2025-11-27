# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_processor module."""

from merino.jobs.navigational_suggestions.processing.domain_processor import DomainProcessor


class TestDomainProcessorExtractTitle:
    """Tests for DomainProcessor._extract_title method."""

    def test_extracts_valid_title(self, mocker):
        """Test extraction of valid title from web scraper."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "Example Website"

        result = processor._extract_title(mock_scraper, "example")

        assert result == "Example Website"

    def test_normalizes_whitespace_in_title(self, mocker):
        """Test that whitespace is normalized in extracted title."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "  Example   Website  "

        result = processor._extract_title(mock_scraper, "example")

        assert result == "Example Website"

    def test_returns_fallback_for_invalid_title(self, mocker):
        """Test that fallback is used for invalid titles like error messages."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "404 Not Found"

        result = processor._extract_title(mock_scraper, "example")

        assert result == "Example"

    def test_returns_fallback_for_none_title(self, mocker):
        """Test that fallback is used when scrape_title returns None."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = None

        result = processor._extract_title(mock_scraper, "mozilla")

        assert result == "Mozilla"

    def test_returns_fallback_for_empty_title(self, mocker):
        """Test that fallback is used for empty string title."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = ""

        result = processor._extract_title(mock_scraper, "test")

        assert result == "Test"

    def test_capitalizes_fallback(self, mocker):
        """Test that fallback domain name is capitalized."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = None

        result = processor._extract_title(mock_scraper, "github")

        assert result == "Github"

    def test_handles_exception_from_scraper(self, mocker):
        """Test that exceptions from scraper are handled gracefully."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.side_effect = Exception("Scraping failed")

        result = processor._extract_title(mock_scraper, "example")

        assert result == "Example"

    def test_handles_bot_detection_title(self, mocker):
        """Test that bot detection messages use fallback."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "Attention Required! | Cloudflare"

        result = processor._extract_title(mock_scraper, "example")

        assert result == "Example"

    def test_preserves_title_with_special_characters(self, mocker):
        """Test that titles with special characters are preserved."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "Stack Overflow - Where Developers Learn"

        result = processor._extract_title(mock_scraper, "stackoverflow")

        assert result == "Stack Overflow - Where Developers Learn"

    def test_handles_access_denied_title(self, mocker):
        """Test that 'Access Denied' titles use fallback."""
        processor = DomainProcessor(blocked_domains=set())
        mock_scraper = mocker.MagicMock()
        mock_scraper.scrape_title.return_value = "Access Denied"

        result = processor._extract_title(mock_scraper, "secure")

        assert result == "Secure"
