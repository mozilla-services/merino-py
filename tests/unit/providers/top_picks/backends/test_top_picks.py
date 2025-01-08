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

from merino.configs import settings
from merino.providers.top_picks.backends.filemanager import GetFileResultCode
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import TopPicksBackend, TopPicksError
from tests.types import FilterCaplogFixture


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
                    "serp_categories": [0],
                    "similars": ["exxample", "exampple", "eexample"],
                },
                {
                    "rank": 2,
                    "title": "Firefox",
                    "domain": "firefox",
                    "url": "https://firefox.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "serp_categories": [0],
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
                    "serp_categories": [0],
                    "similars": ["mozzilla", "mozila"],
                },
                {
                    "rank": 4,
                    "title": "Abc",
                    "domain": "abc",
                    "url": "https://abc.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "serp_categories": [0],
                    "similars": ["aa", "ab", "acb", "acbc", "aecbc"],
                },
                {
                    "rank": 5,
                    "title": "BadDomain",
                    "domain": "baddomain",
                    "url": "https://baddomain.test",
                    "icon": "",
                    "categories": ["web-browser"],
                    "serp_categories": [0],
                    "similars": ["bad", "badd"],
                },
            ]
        }
    )


@pytest.fixture(name="gcs_blob_mock", autouse=True)
def fixture_gcs_blob_mock(mocker: MockerFixture, expected_timestamp: int, blob_json: str) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "20220101120555_top_picks.json"
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


def test_init_failure_no_domain_file(
    top_picks_backend_parameters: dict[str, Any],
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


def test_read_domain_list_json_decode_err(top_picks_backend: TopPicksBackend, mocker) -> None:
    """Test that the read function fails, raising TopPicksError when a
    JSONDecodeError is captured.
    """
    mocker.patch("json.load", side_effect=JSONDecodeError("test", "json", 1))
    with pytest.raises(TopPicksError):
        top_picks_backend.read_domain_list(settings.providers.top_picks.top_picks_file_path)


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
    result_code, result = await top_picks_backend.fetch()
    assert result_code is GetFileResultCode.SUCCESS
    assert hasattr(result, attr)


def test_maybe_build_indicies_local(
    top_picks_backend: TopPicksBackend,
    mocker,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test the local case for building indicies."""
    caplog.set_level(logging.INFO)
    mocker.patch(
        "merino.configs.settings.providers.top_picks.domain_data_source"
    ).return_value = "local"

    get_file_result_code, result = top_picks_backend.maybe_build_indices()

    assert result
    assert get_file_result_code is GetFileResultCode.SUCCESS
    assert isinstance(result, TopPicksData)
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.top_picks.backends.top_picks"
    )
    assert len(records) == 1


def test_maybe_build_indicies_remote(
    top_picks_backend: TopPicksBackend,
    mocker,
    gcs_client_mock,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    gcs_blob_mock,
) -> None:
    """Test remote build indicies method."""
    caplog.set_level(logging.INFO)
    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Client"
    ).return_value = gcs_client_mock
    mocker.patch(
        "merino.configs.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"

    get_file_result_code, result = top_picks_backend.maybe_build_indices()
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.top_picks.backends.top_picks"
    )
    assert get_file_result_code is GetFileResultCode.SUCCESS
    assert isinstance(result, TopPicksData)
    assert len(records) == 1
    assert records[0].message.startswith("Top Picks Domain Data loaded remotely from GCS.")


def test_maybe_build_indicies_remote_fail(
    top_picks_backend: TopPicksBackend,
    mocker,
    gcs_client_mock,
) -> None:
    """Test the catchall case when a source for building indicies
    is not defined.
    """
    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Client"
    ).return_value = gcs_client_mock

    mocker.patch(
        "merino.configs.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"

    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.TopPicksRemoteFilemanager.get_file"
    ).return_value = (GetFileResultCode.FAIL, None)

    get_file_result_code, result = top_picks_backend.maybe_build_indices()

    assert get_file_result_code is GetFileResultCode.FAIL
    assert result is None


def test_maybe_build_indicies_remote_skip(
    top_picks_backend: TopPicksBackend,
    mocker,
    gcs_client_mock,
) -> None:
    """Test the catchall case when a source for building indicies
    is not defined.
    """
    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.Client"
    ).return_value = gcs_client_mock

    mocker.patch(
        "merino.configs.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"

    mocker.patch(
        "merino.providers.top_picks.backends.filemanager.TopPicksRemoteFilemanager.get_file"
    ).return_value = (GetFileResultCode.SKIP, None)

    get_file_result_code, result = top_picks_backend.maybe_build_indices()
    assert get_file_result_code is GetFileResultCode.SKIP
    assert result is None


def test_maybe_build_indicies_error(
    top_picks_backend: TopPicksBackend,
    mocker,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test the catchall case when a source for building indicies
    is not defined.
    """
    mocker.patch(
        "merino.configs.settings.providers.top_picks.domain_data_source"
    ).return_value = "invalid"

    with pytest.raises(ValueError):
        top_picks_backend.maybe_build_indices()
        records: list[LogRecord] = filter_caplog(
            caplog.records, "merino.providers.top_picks.backends.top_picks"
        )
        assert len(records) == 1


def test_domain_blocklist(top_picks_backend: TopPicksBackend, domain_blocklist: set[str]) -> None:
    """Test that the blocked domain, while found in the processed domain data
    is not indexed and therefore not found in any indeces.
    """
    domain_list: list[dict[str, Any]] = top_picks_backend.read_domain_list(
        settings.providers.top_picks.top_picks_file_path
    )["domains"]
    domains: list = [domain["domain"] for domain in domain_list]
    result = top_picks_backend.maybe_build_indices()
    get_file_result_code, top_picks_data = result

    assert get_file_result_code is GetFileResultCode.SUCCESS
    for blocked_domain in domain_blocklist:
        assert blocked_domain in domains
        assert blocked_domain not in top_picks_data.primary_index.keys()  # type: ignore
        assert blocked_domain not in top_picks_data.secondary_index.keys()  # type: ignore
        assert blocked_domain not in top_picks_data.short_domain_index.keys()  # type: ignore
