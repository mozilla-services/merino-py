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
