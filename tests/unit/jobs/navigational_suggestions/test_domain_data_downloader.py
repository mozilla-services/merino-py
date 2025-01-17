# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for domain_data_downloader.py module."""

import pytest
from google.cloud.bigquery.table import Row

from merino.jobs.navigational_suggestions.domain_data_downloader import (
    DomainDataDownloader,
)


@pytest.fixture
def mock_bigquery_client(mocker):
    """Return a mock BigQuery Client instance"""
    return mocker.patch(
        "merino.jobs.navigational_suggestions.domain_data_downloader.Client"
    ).return_value


def test_download_data(mock_bigquery_client):
    """Test if download data returns domain data as expected"""
    mock_bigquery_client.query.return_value.result.return_value = [
        Row(("a", "b"), {"x": 0, "y": 1})
    ]
    domain_data_downloader = DomainDataDownloader("dummy_gcp_project")
    domains = domain_data_downloader.download_data()

    mock_bigquery_client.query.assert_called_once()
    mock_bigquery_client.query.return_value.result.assert_called_once()
    assert domains == [{"x": "a", "y": "b"}]


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
        assert isinstance(domain["categories"], list), f"Categories should be a list in {domain}"
        assert all(
            isinstance(cat, str) for cat in domain["categories"]
        ), f"All categories should be strings in {domain}"
