# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Top Picks backend module."""

import logging
import os
from json import JSONDecodeError
from logging import LogRecord
from typing import Any
from unittest.mock import MagicMock, patch
from google.auth.credentials import AnonymousCredentials
import pytest
from pytest import LogCaptureFixture

from merino.configs import settings
from merino.providers.suggest.top_picks.backends.filemanager import (
    GetFileResultCode,
    TopPicksFilemanagerError,
    TopPicksLocalFilemanager,
    TopPicksRemoteFilemanager,
)
from tests.types import FilterCaplogFixture


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
        "gcs_project_path": settings.image_gcs.gcs_project,
        "gcs_bucket_path": settings.image_gcs.gcs_bucket,
    }


@pytest.fixture(name="top_picks_remote_filemanager")
def fixture_top_picks_remote_filemanager(
    top_picks_remote_filemanager_parameters: dict[str, Any], gcs_client_mock
) -> TopPicksRemoteFilemanager:
    """Create a TopPicksRemoteFilemanager object for test."""
    with (
        patch("merino.utils.gcs.gcs_uploader.Client") as mock_client,
        patch("google.auth.default") as mock_auth_default,
    ):
        creds = AnonymousCredentials()  # type: ignore
        mock_auth_default.return_value = (creds, "test-project")
        mock_client.return_value = gcs_client_mock
        return TopPicksRemoteFilemanager(**top_picks_remote_filemanager_parameters)


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
    test_path = TopPicksLocalFilemanager("./wrongfile.json")
    with pytest.raises(TopPicksFilemanagerError):
        test_path.get_file()


def test_get_file(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    gcs_blob_mock,
) -> None:
    """Test that the Remote Filemanager get_file method returns domain data."""
    top_picks_remote_filemanager.gcs_client = MagicMock()
    top_picks_remote_filemanager.gcs_client.get_file_by_name.return_value = (
        gcs_blob_mock
    )

    caplog.set_level(logging.INFO)
    get_file_result_code, result = top_picks_remote_filemanager.get_file()
    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.suggest.top_picks.backends.filemanager"
    )

    assert isinstance(result, dict)
    assert get_file_result_code is GetFileResultCode.SUCCESS
    assert result["domains"]
    assert len(records) == 1
    assert records[0].message.startswith("Successfully loaded remote domain file.")


def test_get_file_skip(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
) -> None:
    """Test that the Remote Filemanager get_file method returns None and proper skip code."""
    top_picks_remote_filemanager.gcs_client = MagicMock()
    top_picks_remote_filemanager.gcs_client.get_file_by_name.return_value = None

    get_file_result_code, result = top_picks_remote_filemanager.get_file()

    assert get_file_result_code is GetFileResultCode.SKIP
    assert result is None


def test_get_file_error(
    top_picks_remote_filemanager: TopPicksRemoteFilemanager,
) -> None:
    """Test that the Remote Filemanager returns None and correct failure code."""
    top_picks_remote_filemanager.gcs_client = MagicMock()
    top_picks_remote_filemanager.gcs_client.get_file_by_name.side_effect = Exception(
        "Test error"
    )

    get_file_result_code, result = top_picks_remote_filemanager.get_file()
    assert result is None
    assert get_file_result_code is GetFileResultCode.FAIL
