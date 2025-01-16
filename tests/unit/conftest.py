# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the unit test directory."""

from typing import Any
import pytest
from pytest_mock import MockerFixture

from merino.middleware.geolocation import Location
from merino.providers.suggest.base import SuggestionRequest
from tests.unit.types import SuggestionRequestFixture
from google.cloud.storage import Blob, Bucket, Client


@pytest.fixture(scope="session", name="srequest")
def fixture_srequest() -> SuggestionRequestFixture:
    """Return a function that will create a SuggestionRequest object with a given
    `query`
    """

    def srequest(query: str) -> SuggestionRequest:
        """Create a SuggestionRequest object with a given `query`"""
        return SuggestionRequest(query=query, geolocation=Location())

    return srequest


@pytest.fixture(name="expected_timestamp")
def fixture_expected_timestamp() -> int:
    """Return a unix timestamp for metadata mocking."""
    return 16818664520924621


@pytest.fixture(name="gcs_blob_mock", autouse=True)
def fixture_gcs_blob_mock(mocker: MockerFixture, expected_timestamp: int):
    """Return a gcs blob fixture function for testing"""

    def blob_mock(blob_json: str, blob_name: str) -> Any:
        """Create a GCS Blob mock object for testing."""
        mock_blob = mocker.MagicMock(spec=Blob)
        mock_blob.name = blob_name
        mock_blob.generation = expected_timestamp
        mock_blob.download_as_text.return_value = blob_json
        return mock_blob

    return blob_mock


@pytest.fixture(name="gcs_bucket_mock", autouse=True)
def fixture_gcs_bucket_mock(mocker: MockerFixture, gcs_blob_mock) -> Any:
    """Create a GCS Bucket mock object for testing."""
    mock_bucket = mocker.MagicMock(spec=Bucket)
    return mock_bucket


@pytest.fixture(name="gcs_client_mock", autouse=True)
def mock_gcs_client(mocker: MockerFixture):
    """Return a mock GCS Client instance"""
    mock_client = mocker.MagicMock(spec=Client)
    return mock_client
