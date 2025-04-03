# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for _get_serp_categories function in __init__.py."""

import base64
import hashlib

from unittest.mock import patch

from merino.jobs.navigational_suggestions import _get_serp_categories
from merino.providers.suggest.base import Category


def test_get_serp_categories_with_valid_url():
    """Test _get_serp_categories with a valid URL."""

    # Setup a side_effect function for DOMAIN_MAPPING.get
    def mock_get(key, default):
        if (
            key
            == base64.b64encode(
                hashlib.md5("example.com".encode(), usedforsecurity=False).digest()
            ).decode()
        ):
            return [Category.News, Category.Tech]
        return default

    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        mock_domain_mapping.get.side_effect = mock_get

        # Call the function
        result = _get_serp_categories("https://example.com")

        # Verify the results
        assert result == [Category.News.value, Category.Tech.value]
        assert mock_domain_mapping.get.call_count == 1


def test_get_serp_categories_with_none_url():
    """Test _get_serp_categories with None URL."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Call the function with None
        result = _get_serp_categories(None)

        # Verify the result is None
        assert result is None
        mock_domain_mapping.get.assert_not_called()


def test_get_serp_categories_with_subdomain():
    """Test _get_serp_categories with a subdomain."""

    # Setup a side_effect function for DOMAIN_MAPPING.get
    def mock_get(key, default):
        if (
            key
            == base64.b64encode(
                hashlib.md5("sub.example.com".encode(), usedforsecurity=False).digest()
            ).decode()
        ):
            return [Category.Education]
        return default

    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        mock_domain_mapping.get.side_effect = mock_get

        # Call the function
        result = _get_serp_categories("https://sub.example.com/path")

        # Verify the results
        assert result == [Category.Education.value]
        assert mock_domain_mapping.get.call_count == 1


def test_get_serp_categories_with_empty_url():
    """Test _get_serp_categories with an empty URL."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Call the function with empty string
        result = _get_serp_categories("")

        # Verify the result
        assert result is None
        mock_domain_mapping.get.assert_not_called()


def test_get_serp_categories_with_unknown_domain():
    """Test _get_serp_categories with an unknown domain."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # When domain is not found, the default is used
        mock_domain_mapping.get.return_value = [Category.Inconclusive]

        # Call the function
        result = _get_serp_categories("https://unknown-domain.example")

        # Verify the results
        assert result == [Category.Inconclusive.value]
        mock_domain_mapping.get.call_count == 1


def test_get_serp_categories_with_multiple_categories():
    """Test _get_serp_categories with multiple categories."""

    # Setup a side_effect function for DOMAIN_MAPPING.get
    def mock_get(key, default):
        if (
            key
            == base64.b64encode(
                hashlib.md5("multi-category.com".encode(), usedforsecurity=False).digest()
            ).decode()
        ):
            return [Category.Home, Category.Business, Category.Tech]
        return default

    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        mock_domain_mapping.get.side_effect = mock_get

        # Call the function
        result = _get_serp_categories("https://multi-category.com")

        # Verify all categories are included in the result
        assert result == [Category.Home.value, Category.Business.value, Category.Tech.value]
        assert mock_domain_mapping.get.call_count == 1


def test_get_serp_categories_with_invalid_url_format():
    """Test _get_serp_categories with an invalid URL format."""
    # Test with a URL that doesn't contain a host
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Setup the mock to return a default value
        mock_domain_mapping.get.return_value = [Category.Inconclusive]

        # Call the function with a malformed URL
        result = _get_serp_categories("https://")

        # The implementation actually returns the Category.Inconclusive values
        # which is [0] since Inconclusive has value 0
        assert result == [Category.Inconclusive.value]

        # The function actually does call get() with an empty host hash
        mock_domain_mapping.get.assert_called_once()


def test_get_serp_categories_with_port_in_url():
    """Test _get_serp_categories with a URL containing a port number."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Setup mock to verify the correct host is extracted
        def mock_get(key, default):
            # The MD5 hash should be for "example.com", not "example.com:8080"
            expected_host = "example.com"
            expected_key = base64.b64encode(
                hashlib.md5(expected_host.encode(), usedforsecurity=False).digest()
            ).decode()

            if key == expected_key:
                return [Category.Tech]
            return default

        mock_domain_mapping.get.side_effect = mock_get

        # Call the function with a URL containing a port
        result = _get_serp_categories("https://example.com:8080/path")

        # Verify the correct category is returned
        assert result == [Category.Tech.value]
        assert mock_domain_mapping.get.call_count == 1
