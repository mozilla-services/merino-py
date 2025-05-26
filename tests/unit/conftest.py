# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the unit test directory."""

import json
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from google.auth.credentials import AnonymousCredentials
from pytest_mock import MockerFixture

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.base import SuggestionRequest
from tests.unit.types import SuggestionRequestFixture
from google.cloud.storage import Blob, Bucket, Client


@pytest.fixture(scope="session", name="srequest")
def fixture_srequest() -> SuggestionRequestFixture:
    """Return a function that will create a SuggestionRequest object with a given
    `query`
    """

    def srequest(
        query: str, geolocation: Optional[Location] = None, user_agent: Optional[UserAgent] = None
    ) -> SuggestionRequest:
        """Create a SuggestionRequest object with a given `query`"""
        return SuggestionRequest(
            query=query,
            geolocation=geolocation if geolocation else Location(),
            user_agent=user_agent if user_agent else None,
        )

    return srequest


@pytest.fixture(name="gcs_client_mock")
def gcs_client_mock(gcs_bucket_mock):
    """Create a mock Client using AnonymousCredentials."""
    mock = MagicMock(spec=Client)
    mock._credentials = AnonymousCredentials()
    mock._base_connection = None
    mock.project = "test_gcp_uploader_project"
    mock.get_bucket.return_value = gcs_bucket_mock
    return mock


@pytest.fixture(name="gcs_bucket_mock", autouse=True)
def fixture_gcs_bucket_mock(mocker: MockerFixture, gcs_blob_mock) -> Any:
    """Create a GCS Bucket mock object for testing."""
    mock_bucket = mocker.MagicMock(spec=Bucket)
    mock_bucket.get_blob.return_value = gcs_blob_mock
    return mock_bucket


@pytest.fixture(name="expected_timestamp")
def fixture_expected_timestamp() -> int:
    """Return a unix timestamp for metadata mocking."""
    return 16818664520924621


@pytest.fixture(name="gcs_blob_mock", autouse=True)
def fixture_gcs_blob_mock(mocker: MockerFixture, expected_timestamp: int, blob_json: str) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "20220101120555_top_picks.json"
    mock_blob.generation = expected_timestamp
    mock_blob.download_as_text.return_value = blob_json
    return mock_blob


@pytest.fixture(name="blob_json")
def fixture_blob_json() -> str:
    """Return a JSON string for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "domain": "google",
                    "categories": ["Search Engines"],
                    "serp_categories": [0],
                    "url": "https://www.google.com/",
                    "title": "Google",
                    "icon": "",
                },
                {
                    "rank": 2,
                    "domain": "microsoft",
                    "categories": ["Business", "Information Technology"],
                    "serp_categories": [0],
                    "url": "https://www.microsoft.com/",
                    "title": "Microsoft – AI, Cloud, Productivity, Computing, Gaming & Apps",
                    "icon": "https://merino-images.services.mozilla.com/favicons"
                    "/90cdaf487716184e4034000935c605d1633926d348116d198f355a98b8c6cd21_17174.oct",
                },
                {
                    "rank": 3,
                    "domain": "facebook",
                    "categories": ["Social Networks"],
                    "serp_categories": [0],
                    "url": "https://www.facebook.com/",
                    "title": "Log in to Facebook",
                    "icon": "https://merino-images.services.mozilla.com/favicons"
                    "/e673f8818103a583c9a98ee38aa7892d58969ec2a8387deaa46ef6d94e8a3796_4535.png",
                },
                {
                    "rank": 4,
                    "domain": "bbc",
                    "categories": ["News"],
                    "serp_categories": [0],
                    "url": "https://www.bbc.co.uk/",
                    "title": "BBC Home - Breaking News",
                    "icon": "https://merino-images.services.mozilla.com/favicons/bbciconhash_12345.png",
                },
                {
                    "rank": 5,
                    "domain": "cnn",
                    "categories": ["News"],
                    "serp_categories": [0],
                    "url": "https://edition.cnn.com/2025/04/09/entertainment/aimee-lou-wood-teeth-talk-intl-scli/index.html",
                    "title": "‘White Lotus’ star Aimee Lou Wood doesn’t love all the talk about her teeth | CNN",
                    "icon": "https://merino-images.services.mozilla.com/favicons/cnniconhash_98765.png",
                },
            ]
        }
    )


@pytest.fixture(name="manifest_data")
def fixture_manifest_data(blob_json: str) -> ManifestData:
    """Return parsed ManifestData object for testing."""
    return ManifestData.model_validate_json(blob_json)
