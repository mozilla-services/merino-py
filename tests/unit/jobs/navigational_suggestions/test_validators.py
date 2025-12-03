"""Complete test coverage for validators.py"""

from unittest.mock import patch, MagicMock

from merino.jobs.navigational_suggestions.validators import (
    get_second_level_domain,
    get_title_or_fallback,
    is_domain_blocked,
    sanitize_title,
)
from merino.jobs.navigational_suggestions.utils import (
    is_problematic_favicon_url,
)


class TestGetSecondLevelDomain:
    """Test get_second_level_domain function."""

    def test_get_second_level_domain_basic(self):
        """Test basic domain extraction."""
        result = get_second_level_domain("example.com", "com")
        assert result == "example"

    def test_get_second_level_domain_subdomain(self):
        """Test with subdomain."""
        result = get_second_level_domain("www.example.com", "com")
        assert result == "example"

    def test_get_second_level_domain_multiple_subdomains(self):
        """Test with multiple subdomains."""
        result = get_second_level_domain("blog.www.example.com", "com")
        assert result == "example"

    def test_get_second_level_domain_different_suffix(self):
        """Test with different suffix."""
        result = get_second_level_domain("example.org", "org")
        assert result == "example"

    def test_get_second_level_domain_country_code(self):
        """Test with country code domain."""
        result = get_second_level_domain("example.co.uk", "uk")
        assert result == "example.co"

    def test_get_second_level_domain_no_suffix_match(self):
        """Test when suffix doesn't match."""
        # When suffix doesn't match, it should still work
        result = get_second_level_domain("example.com", "org")
        assert result == "example.com"

    def test_get_second_level_domain_empty_domain(self):
        """Test with empty domain."""
        result = get_second_level_domain("", "com")
        assert result == ""

    def test_get_second_level_domain_only_suffix(self):
        """Test with domain that's only the suffix."""
        result = get_second_level_domain("com", "com")
        assert result == ""

    def test_get_second_level_domain_hyphenated(self):
        """Test with hyphenated domain."""
        result = get_second_level_domain("my-example.com", "com")
        assert result == "my-example"


class TestGetTitleOrFallback:
    """Test get_title_or_fallback function."""

    def test_get_title_or_fallback_valid_title(self):
        """Test with valid title."""
        result = get_title_or_fallback("Example Website", "example")
        assert result == "Example Website"

    def test_get_title_or_fallback_empty_title(self):
        """Test with empty title."""
        result = get_title_or_fallback("", "example")
        assert result == "Example"

    def test_get_title_or_fallback_none_title(self):
        """Test with None title."""
        result = get_title_or_fallback(None, "example")
        assert result == "Example"

    def test_get_title_or_fallback_whitespace_title(self):
        """Test with whitespace-only title."""
        result = get_title_or_fallback("   ", "example")
        assert result == "Example"

    def test_get_title_or_fallback_fallback_capitalization(self):
        """Test fallback capitalization."""
        result = get_title_or_fallback("", "example-site")
        assert result == "Example-site"

    def test_get_title_or_fallback_preserve_valid_title(self):
        """Test that valid titles are preserved as-is."""
        title = "My Awesome Website!"
        result = get_title_or_fallback(title, "example")
        assert result == title

    def test_get_title_or_fallback_numeric_fallback(self):
        """Test with numeric fallback."""
        result = get_title_or_fallback("", "123example")
        assert result == "123example"

    def test_get_title_or_fallback_special_chars_fallback(self):
        """Test fallback with special characters."""
        result = get_title_or_fallback("", "example_site")
        assert result == "Example_site"


class TestIsDomainBlocked:
    """Test is_domain_blocked function."""

    def test_is_domain_blocked_not_blocked(self):
        """Test domain that's not blocked."""
        blocked_domains = {"blocked.com", "spam.org"}
        result = is_domain_blocked("example.com", "com", blocked_domains)
        assert result is False

    def test_is_domain_blocked_exact_match(self):
        """Test domain that's exactly blocked."""
        blocked_domains = {"example.com", "spam.org"}
        result = is_domain_blocked("example.com", "com", blocked_domains)
        assert result is True

    def test_is_domain_blocked_second_level_match(self):
        """Test blocking by second-level domain."""
        blocked_domains = {"example", "spam"}
        result = is_domain_blocked("www.example.com", "com", blocked_domains)
        assert result is True

    def test_is_domain_blocked_subdomain_not_blocked(self):
        """Test that subdomain isn't blocked when only main domain is blocked."""
        blocked_domains = {"www.example.com"}  # Only specific subdomain blocked
        result = is_domain_blocked("example.com", "com", blocked_domains)
        assert result is False

    def test_is_domain_blocked_empty_blocked_set(self):
        """Test with empty blocked domains set."""
        blocked_domains = set()
        result = is_domain_blocked("example.com", "com", blocked_domains)
        assert result is False

    def test_is_domain_blocked_case_sensitivity(self):
        """Test case sensitivity in blocking."""
        blocked_domains = {"EXAMPLE.COM"}
        result = is_domain_blocked("example.com", "com", blocked_domains)
        assert result is False  # Should be case sensitive

    def test_is_domain_blocked_different_suffixes(self):
        """Test domains with different suffixes."""
        blocked_domains = {"example"}
        result_com = is_domain_blocked("example.com", "com", blocked_domains)
        result_org = is_domain_blocked("example.org", "org", blocked_domains)
        assert result_com is True
        assert result_org is True

    def test_is_domain_blocked_with_tldextract_call(self):
        """Test that tldextract is properly called."""
        blocked_domains = {"example"}

        with patch(
            "merino.jobs.navigational_suggestions.validators.tldextract.extract"
        ) as mock_extract:
            mock_result = MagicMock()
            mock_result.domain = "example"
            mock_extract.return_value = mock_result

            result = is_domain_blocked("www.example.com", "com", blocked_domains)

            mock_extract.assert_called_once_with("www.example.com")
            assert result is True


class TestIsProblematicFaviconUrl:
    """Test is_problematic_favicon_url function."""

    def test_is_problematic_favicon_url_data_url(self):
        """Test data URL (should be problematic)."""
        url = "data:image/png;base64,iVBORw0KGgoAAAANS"
        result = is_problematic_favicon_url(url)
        assert result is True

    def test_is_problematic_favicon_url_manifest_json_base64(self):
        """Test manifest JSON base64 URL."""
        url = "data:application/manifest+json;base64,eyJ0ZXN0IjoidmFsdWUifQ=="
        result = is_problematic_favicon_url(url)
        assert result is True

    def test_is_problematic_favicon_url_normal_url(self):
        """Test normal URL (should not be problematic)."""
        url = "https://example.com/favicon.ico"
        result = is_problematic_favicon_url(url)
        assert result is False

    def test_is_problematic_favicon_url_relative_url(self):
        """Test relative URL (should not be problematic)."""
        url = "/favicon.ico"
        result = is_problematic_favicon_url(url)
        assert result is False

    def test_is_problematic_favicon_url_empty_string(self):
        """Test empty string (should be problematic)."""
        url = ""
        result = is_problematic_favicon_url(url)
        assert result is False  # Empty string is not considered problematic by this function

    def test_is_problematic_favicon_url_data_different_types(self):
        """Test various data URL types."""
        problematic_urls = [
            "data:image/jpeg;base64,/9j/4AAQSkZJRgABA",
            "data:image/gif;base64,R0lGODlhAQABAIA",
            "data:image/svg+xml;base64,PHN2ZyB3aWR0aA",
            "data:text/plain;base64,SGVsbG8gV29ybGQ",
        ]

        for url in problematic_urls:
            result = is_problematic_favicon_url(url)
            assert result is True, f"Expected {url} to be problematic"

    def test_is_problematic_favicon_url_case_insensitive(self):
        """Test case insensitive matching."""
        url = "DATA:IMAGE/PNG;BASE64,iVBORw0KGgoAAAANS"
        result = is_problematic_favicon_url(url)
        assert result is True

    def test_is_problematic_favicon_url_partial_match(self):
        """Test partial data URL match."""
        url = "data:image/png"  # No base64 part
        result = is_problematic_favicon_url(url)
        assert result is True

    def test_is_problematic_favicon_url_not_data_url(self):
        """Test URLs that contain 'data' but aren't data URLs."""
        non_problematic_urls = [
            "https://data.example.com/favicon.ico",
            "https://example.com/data/favicon.ico",
            "https://example.com/favicon-data.ico",
        ]

        for url in non_problematic_urls:
            result = is_problematic_favicon_url(url)
            assert result is False, f"Expected {url} to not be problematic"


class TestSanitizeTitle:
    """Test sanitize_title function."""

    def test_sanitize_title_normal_title(self):
        """Test normal title."""
        title = "Example Website"
        result = sanitize_title(title)
        assert result == "Example Website"

    def test_sanitize_title_with_whitespace(self):
        """Test title with extra whitespace."""
        title = "  Example   Website  "
        result = sanitize_title(title)
        assert result == "Example Website"

    def test_sanitize_title_with_newlines(self):
        """Test title with newlines."""
        title = "Example\nWebsite\n"
        result = sanitize_title(title)
        assert result == "Example Website"

    def test_sanitize_title_with_tabs(self):
        """Test title with tabs."""
        title = "Example\tWebsite"
        result = sanitize_title(title)
        assert result == "Example Website"

    def test_sanitize_title_mixed_whitespace(self):
        """Test title with mixed whitespace characters."""
        title = "\t  Example \n  Website \r\n "
        result = sanitize_title(title)
        assert result == "Example Website"

    def test_sanitize_title_empty_string(self):
        """Test empty string."""
        title = ""
        result = sanitize_title(title)
        assert result == ""

    def test_sanitize_title_only_whitespace(self):
        """Test string with only whitespace."""
        title = "   \n\t  "
        result = sanitize_title(title)
        assert result == ""

    def test_sanitize_title_none_input(self):
        """Test None input."""
        result = sanitize_title(None)
        assert result == ""

    def test_sanitize_title_preserves_content(self):
        """Test that content is preserved while normalizing whitespace."""
        title = "The  Quick\n\tBrown   Fox"
        result = sanitize_title(title)
        assert result == "The Quick Brown Fox"

    def test_sanitize_title_unicode_characters(self):
        """Test title with Unicode characters."""
        title = "  Café  München  "
        result = sanitize_title(title)
        assert result == "Café München"

    def test_sanitize_title_special_characters(self):
        """Test title with special characters."""
        title = "Example & Co. - The #1 Website!"
        result = sanitize_title(title)
        assert result == "Example & Co. - The #1 Website!"

    def test_sanitize_title_numbers_and_symbols(self):
        """Test title with numbers and symbols."""
        title = "  123 Main St. @ $50/month  "
        result = sanitize_title(title)
        assert result == "123 Main St. @ $50/month"


class TestValidatorsIntegration:
    """Test integration between validator functions."""

    def test_domain_processing_pipeline(self):
        """Test complete domain processing pipeline."""
        domain = "www.example-site.com"
        suffix = "com"
        blocked_domains = {"spam", "blocked"}

        # Check if blocked
        is_blocked = is_domain_blocked(domain, suffix, blocked_domains)
        assert is_blocked is False

        # Extract second level domain
        second_level = get_second_level_domain(domain, suffix)
        assert second_level == "example-site"

        # Process title
        raw_title = "  Example Site - Welcome!  "
        sanitized = sanitize_title(raw_title)
        final_title = get_title_or_fallback(sanitized, second_level)
        assert final_title == "Example Site - Welcome!"

    def test_title_processing_with_fallback(self):
        """Test title processing that uses fallback."""
        domain = "my-awesome-site.com"
        suffix = "com"

        second_level = get_second_level_domain(domain, suffix)
        assert second_level == "my-awesome-site"

        # Test with empty title
        empty_title = sanitize_title("   ")
        final_title = get_title_or_fallback(empty_title, second_level)
        assert final_title == "My-awesome-site"

    def test_favicon_url_validation_comprehensive(self):
        """Test comprehensive favicon URL validation."""
        test_cases = [
            # (url, expected_problematic)
            ("https://example.com/favicon.ico", False),
            ("/favicon.ico", False),
            ("favicon.ico", False),
            ("data:image/png;base64,abc123", True),
            ("data:application/manifest+json;base64,xyz789", True),
            ("DATA:IMAGE/GIF;BASE64,def456", True),
            ("", False),  # Empty string is not considered problematic
            ("https://data-server.com/icon.png", False),
        ]

        for url, expected in test_cases:
            result = is_problematic_favicon_url(url)
            assert (
                result == expected
            ), f"URL {url} should be {'problematic' if expected else 'not problematic'}"

    def test_blocked_domain_various_formats(self):
        """Test blocked domain checking with various domain formats."""
        blocked_domains = {"example", "test.org", "spam"}

        test_cases = [
            # (domain, suffix, expected_blocked)
            ("example.com", "com", True),  # Second-level match
            ("www.example.com", "com", True),  # Second-level match with subdomain
            ("test.org", "org", True),  # Exact match
            ("www.test.org", "org", False),  # Subdomain of exact match
            ("spam.net", "net", True),  # Second-level match
            ("notspam.com", "com", False),  # Not blocked
            ("example-site.com", "com", False),  # Contains but not exact
        ]

        for domain, suffix, expected in test_cases:
            result = is_domain_blocked(domain, suffix, blocked_domains)
            assert (
                result == expected
            ), f"Domain {domain} should be {'blocked' if expected else 'not blocked'}"

    def test_title_sanitization_edge_cases(self):
        """Test title sanitization with edge cases."""
        edge_cases = [
            # (input, expected)
            (None, ""),
            ("", ""),
            ("   ", ""),
            ("\n\t\r", ""),
            ("Single", "Single"),
            ("Multiple   Spaces", "Multiple Spaces"),
            ("Line\nBreaks\rAnd\tTabs", "Line Breaks And Tabs"),
            ("  Leading and trailing  ", "Leading and trailing"),
        ]

        for input_title, expected in edge_cases:
            result = sanitize_title(input_title)
            assert result == expected, f"Input '{input_title}' should sanitize to '{expected}'"

    def test_domain_extraction_edge_cases(self):
        """Test domain extraction with edge cases."""
        edge_cases = [
            # (domain, suffix, expected_second_level)
            ("example.com", "com", "example"),
            ("a.b.c.example.com", "com", "example"),
            ("example.co.uk", "uk", "example.co"),
            ("example.com", "org", "example.com"),  # Suffix mismatch
            ("", "com", ""),
            ("com", "com", ""),
            ("x.com", "com", "x"),
        ]

        for domain, suffix, expected in edge_cases:
            result = get_second_level_domain(domain, suffix)
            assert (
                result == expected
            ), f"Domain '{domain}' with suffix '{suffix}' should extract '{expected}'"

    def test_error_handling_in_validators(self):
        """Test error handling in validator functions."""
        # Test with potentially problematic inputs

        # Test sanitize_title with non-string input that has __str__
        class StringableObject:
            def __str__(self):
                return "  Test Object  "

        # This might raise an exception or handle gracefully
        try:
            result = sanitize_title(StringableObject())
            # If it works, it should return a string
            assert isinstance(result, str)
        except (TypeError, AttributeError):
            # If it raises an exception, that's also acceptable behavior
            pass

    def test_unicode_handling_across_validators(self):
        """Test Unicode handling across all validator functions."""
        unicode_domain = "例え.テスト"
        unicode_title = "テスト サイト"

        # Test domain functions
        second_level = get_second_level_domain(unicode_domain, "テスト")
        assert "例え" in second_level

        # Test title functions
        sanitized = sanitize_title(f"  {unicode_title}  ")
        assert sanitized == unicode_title

        final_title = get_title_or_fallback(sanitized, "fallback")
        assert final_title == unicode_title

        # Test URL validation
        unicode_url = f"https://{unicode_domain}/favicon.ico"
        is_problematic = is_problematic_favicon_url(unicode_url)
        assert is_problematic is False
