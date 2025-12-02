"""Complete test coverage for utils.py"""

from unittest.mock import patch

from merino.jobs.navigational_suggestions.utils import (
    get_base_url,
    fix_url,
    is_valid_url,
    join_url,
    process_favicon_url,
)


class TestGetBaseUrl:
    """Test get_base_url function."""

    def test_get_base_url_basic(self):
        """Test basic URL base extraction."""
        url = "https://example.com/path/to/page"
        result = get_base_url(url)
        assert result == "https://example.com"

    def test_get_base_url_with_port(self):
        """Test URL with port."""
        url = "https://example.com:8080/path"
        result = get_base_url(url)
        assert result == "https://example.com:8080"

    def test_get_base_url_root_path(self):
        """Test URL at root."""
        url = "https://example.com/"
        result = get_base_url(url)
        assert result == "https://example.com"

    def test_get_base_url_no_path(self):
        """Test URL without path."""
        url = "https://example.com"
        result = get_base_url(url)
        assert result == "https://example.com"

    def test_get_base_url_subdomain(self):
        """Test URL with subdomain."""
        url = "https://www.example.com/page"
        result = get_base_url(url)
        assert result == "https://www.example.com"

    def test_get_base_url_http(self):
        """Test HTTP URL."""
        url = "http://example.com/page"
        result = get_base_url(url)
        assert result == "http://example.com"

    def test_get_base_url_with_query_params(self):
        """Test URL with query parameters."""
        url = "https://example.com/page?param=value"
        result = get_base_url(url)
        assert result == "https://example.com"

    def test_get_base_url_with_fragment(self):
        """Test URL with fragment."""
        url = "https://example.com/page#section"
        result = get_base_url(url)
        assert result == "https://example.com"


class TestFixUrl:
    """Test fix_url function."""

    def test_fix_url_empty_string(self):
        """Test with empty string."""
        result = fix_url("")
        assert result == ""

    def test_fix_url_single_slash(self):
        """Test with single slash."""
        result = fix_url("/")
        assert result == ""

    def test_fix_url_protocol_relative(self):
        """Test protocol-relative URL."""
        url = "//example.com/favicon.ico"
        result = fix_url(url)
        assert result == "https://example.com/favicon.ico"

    def test_fix_url_no_protocol(self):
        """Test URL without protocol."""
        url = "example.com/favicon.ico"
        result = fix_url(url)
        assert result == "https://example.com/favicon.ico"

    def test_fix_url_absolute_path_with_base(self):
        """Test absolute path with base URL."""
        url = "/favicon.ico"
        base_url = "https://example.com"
        result = fix_url(url, base_url)
        assert result == "https://example.com/favicon.ico"

    def test_fix_url_absolute_path_without_base(self):
        """Test absolute path without base URL."""
        url = "/favicon.ico"
        result = fix_url(url)
        assert result == ""

    def test_fix_url_absolute_path_with_none_base(self):
        """Test absolute path with None base URL."""
        url = "/favicon.ico"
        result = fix_url(url, None)
        assert result == ""

    def test_fix_url_already_valid_https(self):
        """Test already valid HTTPS URL."""
        url = "https://example.com/favicon.ico"
        result = fix_url(url)
        assert result == "https://example.com/favicon.ico"

    def test_fix_url_already_valid_http(self):
        """Test already valid HTTP URL."""
        url = "http://example.com/favicon.ico"
        result = fix_url(url)
        assert result == "http://example.com/favicon.ico"

    def test_fix_url_relative_path_with_base(self):
        """Test relative path with base URL."""
        url = "images/favicon.ico"
        base_url = "https://example.com/path/"
        result = fix_url(url, base_url)
        assert result == "https://example.com/path/images/favicon.ico"

    def test_fix_url_complex_relative_path(self):
        """Test complex relative path."""
        url = "../images/favicon.ico"
        base_url = "https://example.com/path/subpath/"
        result = fix_url(url, base_url)
        assert result == "https://example.com/path/images/favicon.ico"

    def test_fix_url_relative_path_without_base(self):
        """Test relative path without base URL."""
        url = "relative/path"
        result = fix_url(url)
        assert result == ""


class TestIsValidUrl:
    """Test is_valid_url function."""

    def test_is_valid_url_https(self):
        """Test valid HTTPS URL."""
        url = "https://example.com/favicon.ico"
        result = is_valid_url(url)
        assert result is True

    def test_is_valid_url_http(self):
        """Test valid HTTP URL."""
        url = "http://example.com/favicon.ico"
        result = is_valid_url(url)
        assert result is True

    def test_is_valid_url_custom_protocol(self):
        """Test URL with custom protocol."""
        url = "ftp://example.com/file"
        result = is_valid_url(url)
        assert result is True

    def test_is_valid_url_empty_string(self):
        """Test empty string."""
        result = is_valid_url("")
        assert result is False

    def test_is_valid_url_none(self):
        """Test None value."""
        result = is_valid_url(None)
        assert result is False

    def test_is_valid_url_no_protocol(self):
        """Test URL without protocol."""
        url = "example.com/favicon.ico"
        result = is_valid_url(url)
        assert result is False

    def test_is_valid_url_relative_path(self):
        """Test relative path."""
        url = "/favicon.ico"
        result = is_valid_url(url)
        assert result is False

    def test_is_valid_url_protocol_relative(self):
        """Test protocol-relative URL."""
        url = "//example.com/favicon.ico"
        result = is_valid_url(url)
        assert result is False


class TestJoinUrl:
    """Test join_url function."""

    def test_join_url_basic(self):
        """Test basic URL joining."""
        base = "https://example.com"
        path = "/favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/favicon.ico"

    def test_join_url_with_trailing_slash(self):
        """Test URL joining with trailing slash in base."""
        base = "https://example.com/"
        path = "favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/favicon.ico"

    def test_join_url_absolute_path(self):
        """Test joining with absolute path."""
        base = "https://example.com/subpath"
        path = "/favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/favicon.ico"

    def test_join_url_relative_path(self):
        """Test joining with relative path."""
        base = "https://example.com/path/"
        path = "images/favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/path/images/favicon.ico"

    def test_join_url_complex_base(self):
        """Test joining with complex base URL."""
        base = "https://example.com/path/subpath/page.html"
        path = "../favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/path/favicon.ico"

    def test_join_url_query_params_in_base(self):
        """Test joining when base has query params."""
        base = "https://example.com/page?param=value"
        path = "/favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/favicon.ico"

    def test_join_url_fragment_in_base(self):
        """Test joining when base has fragment."""
        base = "https://example.com/page#section"
        path = "/favicon.ico"
        result = join_url(base, path)
        assert result == "https://example.com/favicon.ico"

    def test_join_url_empty_path(self):
        """Test joining with empty path."""
        base = "https://example.com/page"
        path = ""
        result = join_url(base, path)
        assert result == "https://example.com/page"


class TestProcessFaviconUrl:
    """Test process_favicon_url function."""

    def test_process_favicon_url_basic(self):
        """Test basic favicon URL processing."""
        favicon_url = "/favicon.ico"
        base_url = "https://example.com"
        source = "link"

        result = process_favicon_url(favicon_url, base_url, source)

        assert result is not None
        assert result["href"] == "https://example.com/favicon.ico"
        assert result["_source"] == "link"

    def test_process_favicon_url_absolute_url(self):
        """Test processing absolute favicon URL."""
        favicon_url = "https://cdn.example.com/favicon.ico"
        base_url = "https://example.com"
        source = "meta"

        result = process_favicon_url(favicon_url, base_url, source)

        assert result is not None
        assert result["href"] == "https://cdn.example.com/favicon.ico"
        assert result["_source"] == "meta"

    def test_process_favicon_url_protocol_relative(self):
        """Test processing protocol-relative favicon URL."""
        favicon_url = "//cdn.example.com/favicon.ico"
        base_url = "https://example.com"
        source = "manifest"

        result = process_favicon_url(favicon_url, base_url, source)

        assert result is not None
        assert result["href"] == "//cdn.example.com/favicon.ico"
        assert result["_source"] == "manifest"

    def test_process_favicon_url_problematic_url(self):
        """Test processing problematic favicon URL."""
        favicon_url = "data:image/png;base64,iVBORw0KGgoAAAANS"
        base_url = "https://example.com"
        source = "link"

        with patch(
            "merino.jobs.navigational_suggestions.utils.is_problematic_favicon_url"
        ) as mock_check:
            mock_check.return_value = True

            result = process_favicon_url(favicon_url, base_url, source)

        assert result is None

    def test_process_favicon_url_various_sources(self):
        """Test processing with various source types."""
        favicon_url = "/favicon.ico"
        base_url = "https://example.com"

        sources = ["link", "meta", "manifest", "default"]

        for source in sources:
            result = process_favicon_url(favicon_url, base_url, source)
            assert result is not None
            assert result["_source"] == source
            assert result["href"] == "https://example.com/favicon.ico"

    def test_process_favicon_url_empty_url(self):
        """Test processing empty favicon URL."""
        favicon_url = ""
        base_url = "https://example.com"
        source = "link"

        with patch(
            "merino.jobs.navigational_suggestions.utils.is_problematic_favicon_url"
        ) as mock_check:
            mock_check.return_value = True

            result = process_favicon_url(favicon_url, base_url, source)

        assert result is None

    def test_process_favicon_url_relative_complex(self):
        """Test processing complex relative favicon URL."""
        favicon_url = "../../images/favicon.ico"
        base_url = "https://example.com/path/subpath/"
        source = "link"

        result = process_favicon_url(favicon_url, base_url, source)

        assert result is not None
        assert result["href"] == "https://example.com/images/favicon.ico"
        assert result["_source"] == "link"

    def test_process_favicon_url_http_urls(self):
        """Test processing HTTP URLs (not just HTTPS)."""
        favicon_url = "http://example.com/favicon.ico"
        base_url = "https://example.com"
        source = "link"

        result = process_favicon_url(favicon_url, base_url, source)

        assert result is not None
        assert result["href"] == "http://example.com/favicon.ico"
        assert result["_source"] == "link"


class TestUtilsIntegration:
    """Test integration between utility functions."""

    def test_url_processing_pipeline(self):
        """Test complete URL processing pipeline."""
        # Start with a problematic URL that needs fixing
        original_url = "example.com/path/../favicon.ico"
        base_url = "https://site.com/page/"

        # Fix the URL
        fixed_url = fix_url(original_url, base_url)
        assert fixed_url == "https://example.com/favicon.ico"

        # Validate it
        is_valid = is_valid_url(fixed_url)
        assert is_valid is True

        # Extract base
        base = get_base_url(fixed_url)
        assert base == "https://example.com"

    def test_process_favicon_url_with_all_url_types(self):
        """Test process_favicon_url with various URL types."""
        base_url = "https://example.com"
        source = "link"

        test_cases = [
            # (input_url, expected_contains)
            ("/favicon.ico", "https://example.com/favicon.ico"),
            ("https://cdn.com/icon.png", "https://cdn.com/icon.png"),
            ("//assets.com/favicon.svg", "//assets.com/favicon.svg"),
            ("images/favicon.ico", "https://example.com/images/favicon.ico"),
        ]

        for input_url, expected in test_cases:
            result = process_favicon_url(input_url, base_url, source)
            assert result is not None
            assert result["href"] == expected
            assert result["_source"] == source

    def test_join_url_with_get_base_url(self):
        """Test joining URLs after extracting base URL."""
        complex_url = "https://example.com/path/page.html?param=value#section"
        base = get_base_url(complex_url)

        # Join with the extracted base
        result = join_url(base, "/favicon.ico")
        assert result == "https://example.com/favicon.ico"

    def test_fix_url_edge_cases(self):
        """Test fix_url with various edge cases."""
        test_cases = [
            # (url, base_url, expected)
            ("", None, ""),
            ("/", None, ""),
            ("//cdn.com/icon", None, "https://cdn.com/icon"),
            ("example.com", None, "https://example.com"),
            ("/icon", "https://base.com", "https://base.com/icon"),
            ("https://full.com/icon", "https://base.com", "https://full.com/icon"),
        ]

        for url, base, expected in test_cases:
            result = fix_url(url, base)
            assert result == expected

    def test_url_validation_comprehensive(self):
        """Test comprehensive URL validation scenarios."""
        valid_urls = [
            "https://example.com",
            "http://example.com/path",
            "ftp://files.example.com/file.zip",
            "https://sub.domain.com:8080/path?query=value#fragment",
        ]

        invalid_urls = [
            "",
            None,
            "example.com",
            "/path/file",
            "//protocol-relative.com",
            "just-text",
        ]

        for url in valid_urls:
            assert is_valid_url(url) is True, f"Expected {url} to be valid"

        for url in invalid_urls:
            assert is_valid_url(url) is False, f"Expected {url} to be invalid"

    def test_process_favicon_url_error_handling(self):
        """Test process_favicon_url error handling."""
        # Test with validator that raises exception
        with patch(
            "merino.jobs.navigational_suggestions.utils.is_problematic_favicon_url"
        ) as mock_check:
            mock_check.side_effect = Exception("Validation error")

            result = process_favicon_url("/favicon.ico", "https://example.com", "link")

            # Should handle exception gracefully - behavior depends on implementation
            # but shouldn't crash
            assert result is None or isinstance(result, dict)

    def test_url_functions_with_unicode(self):
        """Test URL functions with Unicode characters."""
        unicode_url = "https://例え.テスト/パス"

        # Test that functions handle Unicode gracefully
        base = get_base_url(unicode_url)
        assert "例え.テスト" in base

        is_valid = is_valid_url(unicode_url)
        assert is_valid is True  # Should be valid since it has protocol

        # Test joining with Unicode
        result = join_url(unicode_url, "/favicon.ico")
        assert "例え.テスト" in result
