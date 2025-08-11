# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_data_downloader.py module."""

from unittest.mock import patch

import pytest
from google.cloud.bigquery.table import Row

from merino.jobs.navigational_suggestions.domain_data_downloader import (
    DomainDataDownloader,
)


@patch("google.auth.default")
@patch("google.cloud.bigquery.Client")
@pytest.fixture
def mock_bigquery_client(mocker):
    """Return a mock BigQuery Client instance"""
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.Client"
    ).return_value


@pytest.fixture
def domain_data_downloader(mock_bigquery_client):
    """Return a DomainDataDownloader instance with a mock BigQuery client"""
    return DomainDataDownloader("dummy_gcp_project")


def test_download_data(mock_bigquery_client):
    """Test if download data returns domain data as expected"""
    mock_bigquery_client.query.return_value.result.return_value = [
        Row(("a", "b"), {"x": 0, "y": 1})
    ]
    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    domains = domain_data_downloader.download_data()

    mock_bigquery_client.query.assert_called_once()
    mock_bigquery_client.query.return_value.result.assert_called_once()
    assert domains[0]["x"] == "a"
    assert domains[0]["y"] == "b"
    assert domains[0]["source"] == "top-picks"  # Test source field for BigQuery domains


def test_custom_domains(mock_bigquery_client):
    """Integration test using the actual custom_domains.json file"""
    mock_bigquery_client.query.return_value.result.return_value = []

    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    domains = domain_data_downloader.download_data()

    assert len(domains) > 0, "No domains were loaded from custom_domains.json"

    expected_domains = {
        "mail.google.com",
        "go.twitch.tv",
        "amazon.ca",
        "github.com",
        "google.com",
        "bing.com",
    }

    found_domains = {domain["domain"] for domain in domains}
    common_domains = expected_domains.intersection(found_domains)

    assert (
        common_domains
    ), f"None of the expected domains {expected_domains} were found in {found_domains}"

    for domain in domains[:5]:
        assert isinstance(domain, dict), f"Domain should be a dict, got {type(domain)}"
        assert "domain" in domain, f"Missing 'domain' in {domain}"
        assert "categories" in domain, f"Missing 'categories' in {domain}"
        assert "source" in domain, f"Missing 'source' in {domain}"
        assert (
            domain["source"] == "custom-domains"
        ), f"Expected source to be 'custom-domains', got {domain['source']}"
        assert isinstance(domain["categories"], list), f"Categories should be a list in {domain}"
        assert all(
            isinstance(cat, str) for cat in domain["categories"]
        ), f"All categories should be strings in {domain}"




def test_parse_custom_domain_basic(domain_data_downloader):
    """Test parsing a basic custom domain"""
    result = domain_data_downloader._parse_custom_domain("example.com", 10)
    assert result["domain"] == "example.com"
    assert result["host"] == "example.com"
    assert result["origin"] == "http://example.com"
    assert result["suffix"] == "com"
    assert result["rank"] == 10
    assert result["categories"] == ["Inconclusive"]


def test_parse_custom_domain_with_scheme(domain_data_downloader):
    """Test parsing a custom domain with scheme"""
    result = domain_data_downloader._parse_custom_domain("http://example.com", 10)
    assert result["domain"] == "example.com"
    assert result["host"] == "example.com"
    assert result["origin"] == "http://example.com"
    assert result["suffix"] == "com"


def test_parse_custom_domain_with_subdomain(domain_data_downloader):
    """Test parsing a custom domain with subdomain"""
    result = domain_data_downloader._parse_custom_domain("sub.example.com", 10)
    assert result["domain"] == "sub.example.com"
    assert result["host"] == "sub.example.com"
    assert result["origin"] == "http://sub.example.com"
    assert result["suffix"] == "com"


def test_parse_custom_domain_with_www(domain_data_downloader):
    """Test parsing a custom domain with www subdomain"""
    result = domain_data_downloader._parse_custom_domain("www.example.com", 10)
    assert result["domain"] == "example.com"
    assert result["host"] == "example.com"
    assert result["origin"] == "http://example.com"
    assert result["suffix"] == "com"


def test_parse_custom_domain_with_path(domain_data_downloader):
    """Test parsing a custom domain with path"""
    result = domain_data_downloader._parse_custom_domain("startsiden.no/sok", 10)
    assert result["domain"] == "startsiden.no/sok"
    assert result["host"] == "startsiden.no/sok"
    assert result["origin"] == "http://startsiden.no/sok"
    assert result["suffix"] == "no"


def test_download_data_with_duplicates(mock_bigquery_client, mocker):
    """Test download_data with duplicates between BigQuery and custom domains"""
    # Create mock BigQuery results with domains that will conflict with custom domains
    mock_bigquery_client.query.return_value.result.return_value = [
        Row(
            (1, "amazon.com", "amazon.com", "http://amazon.com", "com", ["Shopping"]),
            {"rank": 0, "domain": 1, "host": 2, "origin": 3, "suffix": 4, "categories": 5},
        )
    ]

    # Patch the logger
    mock_logger = mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.logger"
    )

    # Patch CUSTOM_DOMAINS to include a duplicate
    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.CUSTOM_DOMAINS",
        ["amazon.com", "newdomain.com"],
    )

    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    domains = domain_data_downloader.download_data()

    # Check that logger was called with info about duplicates
    mock_logger.info.assert_any_call(mocker.ANY)

    # Verify only unique domains were added
    domain_names = [d["domain"] for d in domains]
    assert "amazon.com" in domain_names
    assert domain_names.count("amazon.com") == 1  # Should only appear once
    assert "newdomain.com" in domain_names


def test_download_data_exception_handling(mock_bigquery_client, mocker):
    """Test exception handling in download_data method"""
    mock_bigquery_client.query.return_value.result.return_value = [
        Row(
            (1, "example.com", "example.com", "http://example.com", "com", ["Technology"]),
            {"rank": 0, "domain": 1, "host": 2, "origin": 3, "suffix": 4, "categories": 5},
        )
    ]

    # Mock the _parse_custom_domain method to raise an exception
    mocker.patch.object(
        DomainDataDownloader, "_parse_custom_domain", side_effect=Exception("Test exception")
    )

    # Patch the logger
    mock_logger = mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.logger"
    )

    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    domains = domain_data_downloader.download_data()

    # Check that logger.error was called for the exception
    mock_logger.error.assert_called_once()
    assert "Test exception" in mock_logger.error.call_args[0][0]

    # Should still return the domains from BigQuery
    assert len(domains) == 1
    assert domains[0]["domain"] == "example.com"


def test_download_data_with_subdomain(mock_bigquery_client, mocker):
    """Test that custom domains with subdomains should be included in download_data results"""
    # Mock BigQuery to return example.com
    mock_bigquery_client.query.return_value.result.return_value = [
        Row(
            (1, "example.com", "example.com", "http://example.com", "com", ["Technology"]),
            {"rank": 0, "domain": 1, "host": 2, "origin": 3, "suffix": 4, "categories": 5},
        )
    ]

    mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.CUSTOM_DOMAINS",
        ["sub.example.com"],
    )

    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    assert domain_data_downloader.download_data() == [
        {
            "rank": 1,
            "domain": "example.com",
            "host": "example.com",
            "origin": "http://example.com",
            "suffix": "com",
            "categories": ["Technology"],
            "source": "top-picks",
        },
        {
            "rank": 2,
            "domain": "sub.example.com",
            "host": "sub.example.com",
            "origin": "http://sub.example.com",
            "suffix": "com",
            "categories": ["Inconclusive"],
            "source": "custom-domains",
        },
    ]
