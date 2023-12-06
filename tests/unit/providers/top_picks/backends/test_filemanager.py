# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Top Picks backend module."""
import json
import logging
import os
from json import JSONDecodeError
from logging import LogRecord
from typing import Any

import pytest
from google.cloud.storage import Blob, Bucket, Client
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.top_picks.backends.filemanager import (
    GetFileResultCode,
    TopPicksFilemanagerError,
    TopPicksLocalFilemanager,
    TopPicksRemoteFilemanager,
)
from tests.types import FilterCaplogFixture


@pytest.fixture(name="expected_timestamp")
def fixture_expected_timestamp() -> int:
    """Return a unix timestamp for metadata mocking."""
    return 16818664520924621


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


@pytest.fixture(name="gcs_blob_mock", autouse=True)
def fixture_gcs_blob_mock(
    mocker: MockerFixture, expected_timestamp: int, blob_json: str
) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "1681866452_top_picks_latest.json"
    mock_blob.generation = expected_timestamp
    mock_blob.download_as_text.return_value = blob_json
    return mock_blob


@pytest.fixture(name="gcs_bucket_mock", autouse=True)
def fixture_gcs_bucket_mock(mocker: MockerFixture, gcs_blob_mock) -> Any:
    """Create a GCS Bucket mock object for testing."""
    mock_bucket = mocker.MagicMock(spec=Bucket)
    mock_bucket.get_blob.return_value = gcs_blob_mock
    return mock_bucket


@pytest.fixture(name="gcs_client_mock", autouse=True)
def mock_gcs_client(mocker: MockerFixture, gcs_bucket_mock):
    """Return a mock GCS Client instance"""
    mock_client = mocker.MagicMock(spec=Client)
    mock_client.get_bucket.return_value = gcs_bucket_mock
    return mock_client


@pytest.fixture(name="top_picks_local_filemanager_parameters")
def fixture_top_picks_local_filemanager_parameters() -> dict[str, Any]:
    """Define TopPicksLocalFilemanager parameters for test."""
    # These settings read from testing.toml, not default.toml.
    return {
        "static_file_path": settings.providers.top_picks.top_picks_file_path,
    }


@pytest.fixture(name="top_picks_local_filemanager")
def fixture_top_picks_local_filemanager(
    top_picks_local_filemanager_parameters: dict[str, Any],
) -> TopPicksLocalFilemanager:
    """Create a TopPicksLocalFilemanager object for test."""
    return TopPicksLocalFilemanager(**top_picks_local_filemanager_parameters)


@pytest.fixture(name="top_picks_remote_filemanager_parameters")
def fixture_top_picks_remote_filemanager_parameters() -> dict[str, Any]:
    """Define TopPicksRemoteFilemanager parameters for test."""
    # These settings read from testing.toml, not default.toml.
    return {
        "gcs_project_path": settings.providers.top_picks.gcs_project,
        "gcs_bucket_path": settings.providers.top_picks.gcs_bucket,
    }


@pytest.fixture(name="top_picks_remote_filemanager")
def fixture_top_picks_remote_filemanager(
    top_picks_remote_filemanager_parameters: dict[str, Any],
) -> TopPicksRemoteFilemanager:
    """Create a TopPicksRemoteFilemanager object for test."""
    return TopPicksRemoteFilemanager(**top_picks_remote_filemanager_parameters)


def test_create_gcs_client(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager, mocker, gcs_client_mock
) -> None:
    """Test that create_gcs_client returns the GCS client."""
    mocker.patch(
        "merino.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"

    mocker.patch.object(
        top_picks_remote_filemanager, "create_gcs_client"
    ).return_value = gcs_client_mock
    result = top_picks_remote_filemanager.create_gcs_client()

    assert result
    assert isinstance(result, Client)


def test_local_file_exists() -> None:
    """Test that the Top Picks Nav Query file exists locally"""
    assert os.path.exists(settings.providers.top_picks.top_picks_file_path)


def test_get_local_file(top_picks_local_filemanager: TopPicksLocalFilemanager) -> None:
    """Test that the JSON file containing the domain list can be processed"""
    domain_list = top_picks_local_filemanager.get_file()
    assert domain_list["domains"][0]["domain"] == "example"
    assert len(domain_list["domains"][1]["similars"]) == 5


def test_local_filemanager_get_file_json_decode_error(
    top_picks_local_filemanager: TopPicksLocalFilemanager, mocker
) -> None:
    """Test that the read function fails, raising TopPicksFilemanagerError when a
    JSONDecodeError is captured.
    """
    mocker.patch("json.load", side_effect=JSONDecodeError("test", "json", 1))
    with pytest.raises(TopPicksFilemanagerError):
        top_picks_local_filemanager.get_file()


def test_local_filemanager_get_file_os_error(
    top_picks_local_filemanager: TopPicksLocalFilemanager, mocker
) -> None:
    """Test that the read function fails, raising TopPicksFilemanagerError when an
    OSError is captured.
    """
    mocker.patch("json.load", side_effect=OSError("test", "json", 1))
    with pytest.raises(TopPicksFilemanagerError):
        top_picks_local_filemanager.get_file()


def test_local_filemanager_get_file_invalid_path(
    top_picks_local_filemanager: TopPicksLocalFilemanager, mocker
) -> None:
    """Test that read domain fails and raises TopPicksFilemanagerError
    exception with invalid file path.
    """
    mocker.patch.object(
        top_picks_local_filemanager, "static_file_path", return_value="./wrongfile.json"
    )
    with pytest.raises(TopPicksFilemanagerError):
        top_picks_local_filemanager.get_file()


def test_get_file(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
    mocker,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    gcs_client_mock,
) -> None:
    """Test that the Remote Filemanger get_file method returns domain data."""
    caplog.set_level(logging.INFO)
    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Client"
    ).return_value = gcs_client_mock
    mocker.patch(
        "merino.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"
    get_file_result_code, result = top_picks_remote_filemanager.get_file(
        client=gcs_client_mock
    )
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.top_picks.backends.filemanager"
    )

    # `type: ignore` required as mock testing will never result in `get_file`
    # returning `None` and mypy can't intuit this.
    assert isinstance(result, dict)
    assert get_file_result_code is GetFileResultCode.SUCCESS
    assert result["domains"]
    assert len(records) == 1
    assert records[0].message.startswith("Successfully loaded remote domain file.")


def test_get_file_skip(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
    mocker,
    gcs_client_mock,
    gcs_bucket_mock,
) -> None:
    """Test that the Remote Filemanger get_file method returns None and proper skip code."""
    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Client"
    ).return_value = gcs_client_mock

    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Bucket"
    ).return_value = gcs_bucket_mock

    mocker.patch.object(gcs_bucket_mock, "get_blob").return_value = None

    mocker.patch(
        "merino.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"

    get_file_result_code, result = top_picks_remote_filemanager.get_file(
        client=gcs_client_mock
    )

    assert get_file_result_code is GetFileResultCode.SKIP
    assert result is None


def test_get_file_error(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
    mocker,
) -> None:
    """Test that the Remote Filemanger returns None and correct failure code."""
    get_file_result_code, result = top_picks_remote_filemanager.get_file(
        client=mocker.MagicMock(spec=Client)
    )
    assert result is None
    assert get_file_result_code is GetFileResultCode.FAIL
