# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from unittest.mock import patch, MagicMock
import base64
from hashlib import md5

import pytest

from merino.jobs.navigational_suggestions import (
    prepare_domain_metadata,
    _get_serp_categories,
    _write_xcom_file,
    _construct_partner_manifest,
    _construct_top_picks,
)
from merino.utils.domain_categories.models import Category


def test_prepare_domain_metadata_top_picks_construction():
    """Test whether top pick is constructed properly"""
    # Mock the functionality that would otherwise be executed
    with patch("merino.jobs.navigational_suggestions._run_normal_mode") as mock_run_normal:
        # Call the function with local_mode=False
        prepare_domain_metadata(
            "dummy_src_project",
            "dummy_destination_project",
            "dummy_destination_blob",
            local_mode=False,
        )

        # Verify that _run_normal_mode was called
        mock_run_normal.assert_called_once()


def test_get_serp_categories_with_url():
    """Test _get_serp_categories with a URL."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Set up the mock to return a specific category
        test_url = "https://example.com"
        test_host = "example.com"
        test_hash = md5(test_host.encode(), usedforsecurity=False).digest()
        test_encoded_hash = base64.b64encode(test_hash).decode()

        mock_domain_mapping.get.return_value = [Category.Tech]

        # Call the function
        result = _get_serp_categories(test_url)

        # Verify the result
        assert result == [Category.Tech.value]
        mock_domain_mapping.get.assert_called_once_with(test_encoded_hash, [Category.Inconclusive])


def test_get_serp_categories_with_none_url():
    """Test _get_serp_categories with None URL."""
    result = _get_serp_categories(None)
    assert result is None


def test_get_serp_categories_with_default_category():
    """Test _get_serp_categories when domain is not in mapping."""
    with patch("merino.jobs.navigational_suggestions.DOMAIN_MAPPING") as mock_domain_mapping:
        # Set up the mock to return the default value (not found in mapping)
        mock_domain_mapping.get.return_value = [Category.Inconclusive]

        # Call the function
        result = _get_serp_categories("https://unknown-domain.com")

        # Verify the result uses the default category
        assert result == [Category.Inconclusive.value]


def test_write_xcom_file():
    """Test _write_xcom_file."""
    with patch("builtins.open", MagicMock()) as mock_open, patch("json.dump") as mock_json_dump:
        test_data = {"key": "value"}
        _write_xcom_file(test_data)

        # Verify the file was opened with the correct path
        mock_open.assert_called_once_with("/airflow/xcom/return.json", "w")

        # Verify json.dump was called with the correct data
        file_handle = mock_open.return_value.__enter__.return_value
        mock_json_dump.assert_called_once_with(test_data, file_handle)


def test_construct_partner_manifest_mismatch():
    """Test that _construct_partner_manifest raises an error when lengths don't match."""
    partner_favicon_source = [
        {
            "domain": "partner1.com",
            "url": "https://partner1.com",
            "icon": "https://partner1.com/favicon.ico",
        },
        {
            "domain": "partner2.com",
            "url": "https://partner2.com",
            "icon": "https://partner2.com/favicon.ico",
        },
    ]

    # Only one uploaded favicon but two source items
    uploaded_favicons = [
        "https://cdn.example.com/partner1-favicon.ico",
    ]

    # Should raise ValueError due to length mismatch
    with pytest.raises(ValueError) as excinfo:
        _construct_partner_manifest(partner_favicon_source, uploaded_favicons)

    assert "Mismatch" in str(excinfo.value)


def test_construct_top_picks_with_serp_categories():
    """Test that _construct_top_picks correctly includes SERP categories."""
    with patch("merino.jobs.navigational_suggestions._get_serp_categories") as mock_get_serp:
        # Setup mock to return different categories for different URLs
        mock_get_serp.side_effect = (
            lambda url: [18] if "example" in url else [0]
        )  # Tech=18, Inconclusive=0

        domain_data = [
            {"rank": 1, "categories": ["web"], "source": "top-picks"},
            {"rank": 2, "categories": ["shopping"], "source": "custom-domains"},
        ]

        domain_metadata = [
            {
                "domain": "example.com",
                "url": "https://example.com",
                "title": "Example",
                "icon": "icon1",
            },
            {"domain": "other.com", "url": "https://other.com", "title": "Other", "icon": "icon2"},
        ]

        result = _construct_top_picks(domain_data, domain_metadata)

        # Verify serp_categories values
        assert result["domains"][0]["serp_categories"] == [18]  # Tech category for example.com
        assert result["domains"][1]["serp_categories"] == [0]  # Inconclusive for other.com

        # Verify _get_serp_categories was called correctly
        assert mock_get_serp.call_count == 2
        mock_get_serp.assert_any_call("https://example.com")
        mock_get_serp.assert_any_call("https://other.com")


def test_construct_top_picks_source_field():
    """Test that _construct_top_picks includes the source field in the output JSON data."""
    # Mock input data
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"},
        {"rank": 2, "categories": ["shopping"], "source": "custom-domains"},
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "icon1",
        },
        {"domain": "amazon.ca", "url": "https://amazon.ca", "title": "Amazon", "icon": "icon2"},
    ]

    # Mock _get_serp_categories to avoid dependency
    with patch("merino.jobs.navigational_suggestions._get_serp_categories", return_value=[0]):
        result = _construct_top_picks(domain_data, domain_metadata)

        # Check if source field is included correctly in the results
        assert "domains" in result
        assert len(result["domains"]) == 2
        assert result["domains"][0]["source"] == "top-picks"
        assert result["domains"][1]["source"] == "custom-domains"

        # Check other fields
        assert result["domains"][0]["domain"] == "example.com"
        assert result["domains"][0]["url"] == "https://example.com"
        assert result["domains"][0]["title"] == "Example"
        assert result["domains"][0]["icon"] == "icon1"

        assert result["domains"][1]["domain"] == "amazon.ca"
        assert result["domains"][1]["url"] == "https://amazon.ca"
        assert result["domains"][1]["title"] == "Amazon"
        assert result["domains"][1]["icon"] == "icon2"


def test_construct_top_picks_missing_source_field():
    """Test that _construct_top_picks handles missing source field correctly."""
    # Mock input data with missing source field
    domain_data = [
        {"rank": 1, "categories": ["web"]},  # No source field
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "title": "Example",
            "icon": "icon1",
        }
    ]

    # Mock _get_serp_categories to avoid dependency
    with patch("merino.jobs.navigational_suggestions._get_serp_categories", return_value=[0]):
        result = _construct_top_picks(domain_data, domain_metadata)

        # Check if source field defaults to "top-picks"
        assert "domains" in result
        assert len(result["domains"]) == 1
        assert result["domains"][0]["source"] == "top-picks"


def test_construct_top_picks_with_null_url():
    """Test that _construct_top_picks correctly handles null URL values."""
    domain_data = [
        {"rank": 1, "categories": ["web"], "source": "top-picks"},
        {"rank": 2, "categories": ["shopping"], "source": "custom-domains"},
    ]

    domain_metadata = [
        {
            "domain": "example.com",
            "url": None,  # Null URL
            "title": "Example",
            "icon": "icon1",
        },
        {"domain": "amazon.ca", "url": "https://amazon.ca", "title": "Amazon", "icon": "icon2"},
    ]

    # Mock _get_serp_categories to avoid dependency
    with patch("merino.jobs.navigational_suggestions._get_serp_categories", return_value=[0]):
        result = _construct_top_picks(domain_data, domain_metadata)

        # The first item should be excluded since its URL is None
        assert "domains" in result
        assert len(result["domains"]) == 1
        assert result["domains"][0]["domain"] == "amazon.ca"


# Skip testing _run_local_mode since it requires extensive mocking
# A more focused approach is to test the components individually
def test_construct_top_picks_with_source_field_extensive():
    """Comprehensive test for _construct_top_picks function."""
    # This test doesn't require complex patching for the _run_local_mode function

    # Create test data with all required fields
    domain_data = [
        {"rank": 1, "categories": ["Technology"], "source": "top-picks", "domain": "example.com"},
        {
            "rank": 2,
            "categories": ["Shopping"],
            "source": "custom-domains",
            "domain": "store.example.com",
        },
    ]

    domain_metadata = [
        {
            "domain": "example",
            "url": "https://example.com",
            "title": "Example Website",
            "icon": "https://example.com/favicon.ico",
        },
        {
            "domain": "store",
            "url": "https://store.example.com",
            "title": "Example Store",
            "icon": "https://store.example.com/favicon.ico",
        },
    ]

    # Use a patch to avoid calling the real _get_serp_categories
    with patch("merino.jobs.navigational_suggestions._get_serp_categories", return_value=[0]):
        result = _construct_top_picks(domain_data, domain_metadata)

    # Verify the result structure and content
    assert "domains" in result
    assert len(result["domains"]) == 2

    # Check first domain
    assert result["domains"][0]["rank"] == 1
    assert result["domains"][0]["domain"] == "example"
    assert result["domains"][0]["categories"] == ["Technology"]
    assert result["domains"][0]["url"] == "https://example.com"
    assert result["domains"][0]["title"] == "Example Website"
    assert result["domains"][0]["icon"] == "https://example.com/favicon.ico"
    assert result["domains"][0]["source"] == "top-picks"

    # Check second domain
    assert result["domains"][1]["rank"] == 2
    assert result["domains"][1]["domain"] == "store"
    assert result["domains"][1]["categories"] == ["Shopping"]
    assert result["domains"][1]["url"] == "https://store.example.com"
    assert result["domains"][1]["title"] == "Example Store"
    assert result["domains"][1]["icon"] == "https://store.example.com/favicon.ico"
    assert result["domains"][1]["source"] == "custom-domains"


def test_construct_top_picks_with_all_required_fields():
    """Test that _construct_top_picks handles all required fields correctly."""
    # Create test data with all required fields including categories
    domain_data = [
        {
            "rank": 1,
            "categories": ["Technology", "Search"],
            "source": "top-picks",
            "domain": "google.com",
        }
    ]

    domain_metadata = [
        {
            "domain": "google",
            "url": "https://google.com",
            "title": "Google",
            "icon": "https://google.com/favicon.ico",
        }
    ]

    # Patch _get_serp_categories to return a known value
    with patch("merino.jobs.navigational_suggestions._get_serp_categories", return_value=[18]):
        result = _construct_top_picks(domain_data, domain_metadata)

    # Verify the structure and content
    assert "domains" in result
    assert len(result["domains"]) == 1

    domain = result["domains"][0]
    assert domain["rank"] == 1
    assert domain["domain"] == "google"
    assert domain["categories"] == ["Technology", "Search"]
    assert domain["serp_categories"] == [18]
    assert domain["url"] == "https://google.com"
    assert domain["title"] == "Google"
    assert domain["icon"] == "https://google.com/favicon.ico"
    assert domain["source"] == "top-picks"


def test_construct_partner_manifest_complete():
    """Test the complete functionality of _construct_partner_manifest."""
    partner_favicons = [
        {
            "domain": "example.com",
            "url": "https://example.com",
            "icon": "https://example.com/favicon.ico",
        },
        {
            "domain": "mozilla.org",
            "url": "https://mozilla.org",
            "icon": "https://mozilla.org/favicon.ico",
        },
    ]

    uploaded_favicons = [
        "https://cdn.example.com/favicons/example-favicon.ico",
        "https://cdn.example.com/favicons/mozilla-favicon.ico",
    ]

    result = _construct_partner_manifest(partner_favicons, uploaded_favicons)

    # Verify structure
    assert "partners" in result
    assert len(result["partners"]) == 2

    # Check first partner
    assert result["partners"][0]["domain"] == "example.com"
    assert result["partners"][0]["url"] == "https://example.com"
    assert result["partners"][0]["original_icon_url"] == "https://example.com/favicon.ico"
    assert (
        result["partners"][0]["gcs_icon_url"]
        == "https://cdn.example.com/favicons/example-favicon.ico"
    )

    # Check second partner
    assert result["partners"][1]["domain"] == "mozilla.org"
    assert result["partners"][1]["url"] == "https://mozilla.org"
    assert result["partners"][1]["original_icon_url"] == "https://mozilla.org/favicon.ico"
    assert (
        result["partners"][1]["gcs_icon_url"]
        == "https://cdn.example.com/favicons/mozilla-favicon.ico"
    )
