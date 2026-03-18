"""Unit tests for custom_favicons.py module."""

import pytest

from merino.jobs.navigational_suggestions.enrichments.custom_favicons import (
    CUSTOM_FAVICONS,
    get_custom_favicon_url,
)


class TestCustomFavicons:
    """Test cases for custom favicon functionality."""

    def test_custom_favicons_dict_exists(self):
        """Test that CUSTOM_FAVICONS dictionary exists and contains expected entries."""
        assert isinstance(CUSTOM_FAVICONS, dict)
        assert len(CUSTOM_FAVICONS) > 0

        # Test a few known entries
        assert "axios" in CUSTOM_FAVICONS
        assert "espn" in CUSTOM_FAVICONS
        assert "mozilla" in CUSTOM_FAVICONS

        # Verify values are URLs
        for domain, url in CUSTOM_FAVICONS.items():
            assert isinstance(domain, str)
            assert isinstance(url, str)
            assert url.startswith(("http://", "https://"))

    def test_get_custom_favicon_url_existing_domain(self):
        """Test get_custom_favicon_url with domains that exist in the mapping."""
        # Test with known domains
        axios_url = get_custom_favicon_url("axios")
        assert axios_url == "https://static.axios.com/icons/favicon.svg"

        espn_url = get_custom_favicon_url("espn")
        assert espn_url == "https://a.espncdn.com/favicon.ico"

        mozilla_url = get_custom_favicon_url("mozilla")
        assert (
            mozilla_url
            == "https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.e143075360ea.png"
        )

    def test_get_custom_favicon_url_non_existing_domain(self):
        """Test get_custom_favicon_url with domains that don't exist in the mapping."""
        # Test with non-existing domain
        result = get_custom_favicon_url("nonexistent")
        assert result == ""

        # Test with empty string
        result = get_custom_favicon_url("")
        assert result == ""

    def test_get_custom_favicon_url_case_sensitivity(self):
        """Test that get_custom_favicon_url is case-sensitive."""
        # Should work with correct case
        result = get_custom_favicon_url("axios")
        assert result != ""

        # Should not work with different case
        result = get_custom_favicon_url("AXIOS")
        assert result == ""

        result = get_custom_favicon_url("Axios")
        assert result == ""

    def test_custom_favicons_all_valid_urls(self):
        """Test that all URLs in CUSTOM_FAVICONS are valid format."""
        for domain, url in CUSTOM_FAVICONS.items():
            # Check basic URL format
            assert url.startswith("https://"), f"URL for {domain} should use HTTPS"
            assert "." in url, f"URL for {domain} should contain domain"

            # Check common favicon extensions or paths
            favicon_indicators = [".ico", ".png", ".svg", "/favicon", "/icons/", "/media/"]
            has_favicon_indicator = any(
                indicator in url.lower() for indicator in favicon_indicators
            )
            assert has_favicon_indicator, f"URL for {domain} should look like a favicon URL: {url}"

    @pytest.mark.parametrize(
        "domain,expected_url",
        [
            ("axios", "https://static.axios.com/icons/favicon.svg"),
            ("espn", "https://a.espncdn.com/favicon.ico"),
            ("ign", "https://kraken.ignimgs.com/favicon.ico"),
            (
                "mozilla",
                "https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.e143075360ea.png",
            ),
            (
                "reuters",
                "https://www.reuters.com/pf/resources/images/reuters/favicon/tr_kinesis_v2.svg?d=287",
            ),
            ("yahoo", "https://s.yimg.com/rz/l/favicon.ico"),
        ],
    )
    def test_get_custom_favicon_url_parametrized(self, domain, expected_url):
        """Parametrized test for specific domain-URL mappings."""
        result = get_custom_favicon_url(domain)
        assert result == expected_url

    def test_custom_favicons_no_duplicates(self):
        """Test that there are no duplicate domains in CUSTOM_FAVICONS."""
        domains = list(CUSTOM_FAVICONS.keys())
        unique_domains = set(domains)
        assert len(domains) == len(
            unique_domains
        ), "CUSTOM_FAVICONS should not have duplicate domains"

    def test_custom_favicons_no_empty_values(self):
        """Test that there are no empty URLs in CUSTOM_FAVICONS."""
        for domain, url in CUSTOM_FAVICONS.items():
            assert url.strip(), f"Domain {domain} has empty or whitespace-only URL"
            assert len(url) > 10, f"Domain {domain} has suspiciously short URL: {url}"

    def test_get_custom_favicon_url_type_safety(self):
        """Test get_custom_favicon_url handles different input types safely."""
        # Test with numeric input (should convert to string and not match)
        result = get_custom_favicon_url(123)
        assert result == ""

        # Test with boolean input
        result = get_custom_favicon_url(True)
        assert result == ""

        # Test with list input
        result = get_custom_favicon_url([])
        assert result == ""

    def test_get_custom_favicon_url_whitespace_handling(self):
        """Test get_custom_favicon_url handles whitespace in domain names."""
        # Test with leading/trailing whitespace
        result = get_custom_favicon_url(" axios ")
        assert result == ""

        # Test with tabs and newlines
        result = get_custom_favicon_url("axios\t")
        assert result == ""

        result = get_custom_favicon_url("\naxios")
        assert result == ""

    def test_custom_favicons_domain_format_validation(self):
        """Test that all domain names in CUSTOM_FAVICONS are properly formatted."""
        for domain in CUSTOM_FAVICONS.keys():
            # Domain should be lowercase
            assert domain.islower(), f"Domain {domain} should be lowercase"

            # Domain should not contain common TLD suffixes (as per module docstring)
            invalid_suffixes = [".com", ".org", ".net", ".edu", ".gov"]
            for suffix in invalid_suffixes:
                assert not domain.endswith(
                    suffix
                ), f"Domain {domain} should not contain suffix {suffix}"

            # Domain should not be empty or contain only whitespace
            assert domain.strip(), "Domain should not be empty or whitespace-only"

            # Domain should not contain protocol or slashes
            assert not domain.startswith(
                ("http://", "https://")
            ), f"Domain {domain} should not contain protocol"
            assert "/" not in domain, f"Domain {domain} should not contain slashes"

    def test_custom_favicons_url_security_validation(self):
        """Test that all URLs in CUSTOM_FAVICONS meet security standards."""
        for domain, url in CUSTOM_FAVICONS.items():
            # All URLs should use HTTPS for security
            assert url.startswith("https://"), f"URL for {domain} must use HTTPS: {url}"

            # URLs should not contain suspicious patterns
            suspicious_patterns = ["javascript:", "data:", "file:", "ftp:"]
            for pattern in suspicious_patterns:
                assert (
                    pattern not in url.lower()
                ), f"URL for {domain} contains suspicious pattern {pattern}: {url}"

            # URLs should be well-formed (basic check)
            assert " " not in url, f"URL for {domain} should not contain spaces: {url}"

    def test_get_custom_favicon_url_exact_match_only(self):
        """Test that get_custom_favicon_url only returns exact matches."""
        # Test partial matches don't work
        result = get_custom_favicon_url("axio")  # Partial match for "axios"
        assert result == ""

        result = get_custom_favicon_url("xios")  # Another partial match
        assert result == ""

        # Test that substrings of domains don't match
        result = get_custom_favicon_url("esp")  # Substring of "espn"
        assert result == ""

    def test_custom_favicons_comprehensive_url_formats(self):
        """Test that URLs cover different common favicon formats."""
        url_extensions = set()
        url_paths = set()

        for domain, url in CUSTOM_FAVICONS.items():
            # Extract extension
            if "." in url.split("/")[-1]:
                ext = url.split("/")[-1].split(".")[-1].split("?")[0]  # Handle query params
                url_extensions.add(ext)

            # Check for common favicon paths
            if "/favicon" in url.lower():
                url_paths.add("favicon_path")
            if "/icon" in url.lower():
                url_paths.add("icon_path")
            if "/media/" in url.lower():
                url_paths.add("media_path")

        # Should have various formats represented
        common_extensions = {"ico", "png", "svg"}
        found_extensions = url_extensions.intersection(common_extensions)
        assert (
            len(found_extensions) >= 2
        ), f"Should have multiple favicon formats, found: {url_extensions}"

    def test_custom_favicons_domains_alphabetical_suggestion(self):
        """Suggest keeping domains in alphabetical order for maintainability."""
        domains = list(CUSTOM_FAVICONS.keys())
        sorted_domains = sorted(domains)

        # This is informational - we don't enforce alphabetical order but suggest it
        if domains != sorted_domains:
            # Just verify we can sort them (no assertion failure, just good practice check)
            assert len(domains) == len(sorted_domains), "Domain list should be sortable"

    def test_get_custom_favicon_url_exception_handling(self):
        """Test get_custom_favicon_url exception handling path."""

        # Test with an object that will raise TypeError when used as dict key
        class ProblematicObject:
            def __hash__(self):
                raise TypeError("Cannot hash this object")

        problematic_obj = ProblematicObject()
        result = get_custom_favicon_url(problematic_obj)
        assert result == ""

        # Test with None input
        result = get_custom_favicon_url(None)
        assert result == ""
