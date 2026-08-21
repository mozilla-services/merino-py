# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_processor module."""

import pytest

from merino.configs import settings
from merino.jobs.navigational_suggestions.processing.domain_processor import DomainProcessor


class TestDomainProcessorIsMatchingDomain:
    """Tests for DomainProcessor._is_matching_domain static method."""

    def test_exact_substring_match(self):
        """Test original behavior: domain substring found in URL."""
        assert DomainProcessor._is_matching_domain("example.com", "https://www.example.com/page")

    def test_tld_change_accepted(self):
        """Test TLD changes are accepted (e.g., zoom.us -> zoom.com)."""
        assert DomainProcessor._is_matching_domain("zoom.us", "https://www.zoom.com")

    def test_cctld_change_accepted(self):
        """Test country-code TLD changes (e.g., wired.co.uk -> wired.com)."""
        assert DomainProcessor._is_matching_domain("wired.co.uk", "https://www.wired.com/")

    def test_different_domain_rejected(self):
        """Test genuinely different domains are rejected."""
        assert not DomainProcessor._is_matching_domain("t.me", "https://telegram.org/")

    def test_different_brand_redirect_rejected(self):
        """Test redirects to different brands are rejected."""
        assert not DomainProcessor._is_matching_domain("uw.edu", "https://www.washington.edu/")

    def test_subdomain_in_redirect(self):
        """Test domain with www prefix in redirect URL."""
        assert DomainProcessor._is_matching_domain("example.com", "https://www.example.com/")


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


class TestDomainProcessorTryCustomFavicon:
    """Tests for DomainProcessor._try_custom_favicon method."""

    @pytest.mark.asyncio
    async def test_passes_cache_control_to_upload_image(self, mocker):
        """Test that the configured cache_control setting is passed to upload_image."""
        mocker.patch(
            "merino.jobs.navigational_suggestions.processing.domain_processor."
            "get_custom_favicon_url",
            return_value="https://example.com/favicon.ico",
        )

        downloader_mock = mocker.AsyncMock()
        downloader_mock.download_favicon.return_value = b"favicon-bytes"
        processor = DomainProcessor(blocked_domains=set(), favicon_downloader=downloader_mock)

        uploader_mock = mocker.MagicMock()
        uploader_mock.uploader.cdn_hostname = "cdn.example.net"
        uploader_mock.force_upload = False
        uploader_mock.destination_favicon_name.return_value = "favicons/favicon.ico"
        uploader_mock.upload_image.return_value = "https://cdn.example.net/favicons/favicon.ico"

        result = await processor._try_custom_favicon(
            domain_key="example",
            full_domain="www.example.com",
            second_level_domain="example",
            uploader=uploader_mock,
        )

        assert result is not None
        uploader_mock.upload_image.assert_called_once_with(
            b"favicon-bytes",
            "favicons/favicon.ico",
            forced_upload=uploader_mock.force_upload,
            cache_control=settings.jobs.navigational_suggestions.cache_control,
        )
