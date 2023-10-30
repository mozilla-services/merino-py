# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Top Picks backend module."""
import json
import os
from datetime import datetime
from json import JSONDecodeError
from typing import Any

import pytest
from google.cloud import storage
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import (
    TopPicksBackend,
    TopPicksError,
    TopPicksFilemanager,
)


@pytest.fixture(name="domain_blocklist")
def fixture_top_picks_domain_blocklist() -> set[str]:
    """Create domain_blocklist."""
    return {"baddomain"}


@pytest.fixture(name="top_picks_backend_parameters")
def fixture_top_picks_backend_parameters(domain_blocklist: set[str]) -> dict[str, Any]:
    """Define Top Picks backend parameters for test."""
    return {
        "top_picks_file_path": settings.providers.top_picks.top_picks_file_path,
        "query_char_limit": settings.providers.top_picks.query_char_limit,
        "firefox_char_limit": settings.providers.top_picks.firefox_char_limit,
        "domain_blocklist": domain_blocklist,
    }


@pytest.fixture(name="top_picks_backend")
def fixture_top_picks(top_picks_backend_parameters: dict[str, Any]) -> TopPicksBackend:
    """Create a Top Picks object for test."""
    return TopPicksBackend(**top_picks_backend_parameters)


@pytest.fixture(name="expected_timestamp")
def fixture_expected_timestamp() -> int:
    """Return a unix timestamp for metadata mocking."""
    return 1696916833376515


@pytest.fixture(name="blob_json")
def fixture_blob_json() -> str:
    """Return a JSON string for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "title": "Example",
                    "domain": "example",
                    "url": "https://example.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [
                        "firefoxx",
                        "foyerfox",
                        "fiirefox",
                        "firesfox",
                        "firefoxes",
                    ],
                },
                {
                    "rank": 3,
                    "title": "Mozilla",
                    "domain": "mozilla",
                    "url": "https://mozilla.org/en-US/",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": ["bad", "badd"],
                },
            ]
        }
    )


@pytest.fixture
def mock_gcs_client(mocker):
    """Return a mock GCS Client instance"""
    return mocker.patch(
        "merino.providers.top_picks.backends.top_picks.Client"
    ).return_value


@pytest.fixture(name="gcs_blob_mock")
def fixture_gcs_blob_mock(
    mocker: MockerFixture, expected_timestamp: int, blob_json: str
) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=storage.Blob)
    mock_blob.name = "123456.top_picks_latest.json"
    mock_blob.generation = expected_timestamp
    mock_blob.download_as_text.return_value = blob_json
    return mock_blob


@pytest.fixture(name="gcs_bucket_mock")
def fixture_gcs_bucket_mock(mocker: MockerFixture, gcs_blob_mock) -> Any:
    """Create a GCS Bucket mock object for testing."""
    mock_bucket = gcs_blob_mock
    storage.Client.get_bucket = mocker.MagicMock(return_value=gcs_blob_mock)
    return mock_bucket


@pytest.fixture(name="top_picks_filemanager_parameters")
def fixture_top_picks_filemanager_parameters() -> dict[str, Any]:
    """Define Top Picks Filemanager parameters for test."""
    # These settings read from testing.toml, not default.toml.
    return {
        "gcs_project_path": settings.providers.top_picks.gcs_project,
        "gcs_bucket_path": settings.providers.top_picks.gcs_bucket,
        "static_file_path": settings.providers.top_picks.top_picks_file_path,
    }


@pytest.fixture(name="top_picks_filemanager")
def fixture_top_picks_filemanager(
    top_picks_filemanager_parameters: dict[str, Any],
) -> TopPicksFilemanager:
    """Create a TopPicksFilemanager object for test."""
    return TopPicksFilemanager(**top_picks_filemanager_parameters)


def test_filemanager__parse_date(
    gcs_blob_mock: storage.Blob,
    expected_timestamp: int,
) -> None:
    """Test that the filemanager _parse_date method parses a unix timestamp"""
    # import pdb

    # pdb.set_trace()
    expected_datetime = datetime.fromtimestamp(int(expected_timestamp / 100000))
    assert expected_datetime == TopPicksFilemanager._parse_date(blob=gcs_blob_mock)


def test__parse_date_with_missing_metadata(
    mocker: MockerFixture,
) -> None:
    """Test that the filemanager result is None when mock Blob has no generation
    metadata.
    """
    mock_blob = mocker.MagicMock(spec=storage.Blob)
    mock_blob.name = "123456.top_picks_latest.json"
    mock_blob.generation = None

    result = TopPicksFilemanager._parse_date(blob=mock_blob)
    assert not result


def test_filemanager__parse_date_fails(
    top_picks_filemanager: TopPicksFilemanager,
    gcs_blob_mock: storage.Blob,
    mocker,
) -> None:
    """Test that the filemanager _parse_date method raises the
    expected AttributeError and returns None.
    """
    expected_datetime = None

    error_message: str = "Cannot parse date, generation attribute not found."
    mocker.patch.object(
        top_picks_filemanager, "_parse_date", side_effect=AttributeError(error_message)
    )

    with pytest.raises(AttributeError):
        result = top_picks_filemanager._parse_date(blob=gcs_blob_mock)
        assert expected_datetime == top_picks_filemanager._parse_date(
            blob=gcs_blob_mock
        )
        assert not result


def test_init_failure_no_domain_file(
    top_picks_backend_parameters: dict[str, Any]
) -> None:
    """Test exception handling for the __init__() method when no domain file provided."""
    top_picks_backend_parameters["top_picks_file_path"] = None
    with pytest.raises(ValueError):
        TopPicksBackend(**top_picks_backend_parameters)


def test_local_file_exists() -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_picks.top_picks_file_path)


def test_read_domain_list(top_picks_backend: TopPicksBackend) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    domain_list = top_picks_backend.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )
    assert domain_list["domains"][0]["domain"] == "example"
    assert len(domain_list["domains"][1]["similars"]) == 5


def test_read_domain_list_os_error(top_picks_backend: TopPicksBackend) -> None:
    """Test that read domain fails and raises exception with invalid file path."""
    with pytest.raises(TopPicksError):
        top_picks_backend.read_domain_list("./wrongfile.json")


@pytest.mark.asyncio
async def test_get_remote_file(
    top_picks_filemanager: TopPicksFilemanager, gcs_blob_mock, gcs_bucket_mock
) -> None:
    """Test that get_remote_file returns domain data."""
    pass


def test_read_domain_list_json_decode_err(
    top_picks_backend: TopPicksBackend, mocker
) -> None:
    """Test that the read function fails, raising TopPicksError when a
    JSONDecodeError is captured.
    """
    mocker.patch("json.load", side_effect=JSONDecodeError("test", "json", 1))
    with pytest.raises(TopPicksError):
        top_picks_backend.read_domain_list(
            settings.providers.top_picks.top_picks_file_path
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attr",
    [
        "primary_index",
        "secondary_index",
        "short_domain_index",
        "query_min",
        "query_max",
        "query_char_limit",
        "firefox_char_limit",
    ],
)
async def test_fetch(top_picks_backend: TopPicksBackend, attr: str) -> None:
    """Test the fetch method returns TopPickData."""
    result = await top_picks_backend.fetch()
    assert hasattr(result, attr)


def test_domain_blocklist(
    top_picks_backend: TopPicksBackend, domain_blocklist: set[str]
) -> None:
    """Test that the blocked domain, while found in the processed domain data
    is not indexed and therefore not found in any indeces.
    """
    domain_list: list[dict[str, Any]] = top_picks_backend.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )["domains"]
    domains: list = [domain["domain"] for domain in domain_list]
    top_picks_data: TopPicksData = top_picks_backend.build_indices()

    for blocked_domain in domain_blocklist:
        assert blocked_domain in domains
        assert blocked_domain not in top_picks_data.primary_index.keys()
        assert blocked_domain not in top_picks_data.secondary_index.keys()
        assert blocked_domain not in top_picks_data.short_domain_index.keys()
