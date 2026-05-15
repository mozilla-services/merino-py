# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle filemanager module."""

import logging
import os
import pytest

from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Blob
from json import JSONDecodeError
from logging import LogRecord
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from tests.types import FilterCaplogFixture
from typing import Any
from unittest.mock import MagicMock, patch

from merino.configs import settings
from merino.providers.games.particle.backends.filemanager import (
    ParticleFileManagerError,
    ParticleLocalFileManager,
    ParticleRemoteFileManager,
)
from merino.utils.gcs.gcs_uploader import GcsUploader


@pytest.fixture(name="manifest_json")
def fixture_manifest_json():
    """Load manifest data from local file"""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="manifest_gcs_blob_mock")
def fixture_gcs_manifest_blob(mocker: MockerFixture, manifest_json: str) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "runtime-manifest.v1.json"
    mock_blob.download_as_text.return_value = manifest_json

    return mock_blob


@pytest.fixture(name="particle_local_filemanager_parameters")
def fixture_particle_local_filemanager_parameters() -> dict[str, Any]:
    """Define ParticleLocalFileManager parameters for test."""
    return {
        "static_manifest_schema_file_path": settings.games_providers.particle.manifest_schema_file_path
    }


@pytest.fixture(name="particle_local_filemanager")
def fixture_particle_local_filemanager(
    particle_local_filemanager_parameters: dict[str, Any],
) -> ParticleLocalFileManager:
    """Create a ParticleLocalFileManager object for test."""
    return ParticleLocalFileManager(**particle_local_filemanager_parameters)


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock(manifest_gcs_blob_mock) -> GcsUploader:
    """Return a mock GcsUploader."""
    mock = MagicMock(spec=GcsUploader)
    mock.get_file_by_name.return_value = manifest_gcs_blob_mock

    return mock


@pytest.fixture(name="particle_remote_filemanager_parameters")
def fixture_particle_remote_filemanager_parameters(gcs_uploader_mock) -> dict[str, Any]:
    """Define ParticleRemoteFileManager parameters for test."""
    return {"gcs_client": gcs_uploader_mock, "manifest_file_name": "test_file.json"}


@pytest.fixture(name="particle_remote_filemanager")
def fixture_particle_remote_filemanager(
    particle_remote_filemanager_parameters: dict[str, Any],
) -> ParticleRemoteFileManager:
    """Create a ParticleRemoteFileManager object for test."""
    with (
        patch("google.auth.default") as mock_auth_default,
    ):
        creds = AnonymousCredentials()  # type: ignore
        mock_auth_default.return_value = (creds, "test-project")
        return ParticleRemoteFileManager(**particle_remote_filemanager_parameters)


def test_local_file_exists() -> None:
    """Test that the Particle manifest schema file exists locally"""
    assert os.path.exists(settings.games_providers.particle.manifest_schema_file_path)


def test_get_local_file(particle_local_filemanager: ParticleLocalFileManager) -> None:
    """Test that the JSON file containing the manifest schema can be processed"""
    schema = particle_local_filemanager.get_manifest_schema()
    assert schema["title"] == "Client Runtime Manifest v1"
    assert len(schema["properties"]["channels"]["properties"]) == 2


def test_local_filemanager_get_file_json_decode_error(
    particle_local_filemanager: ParticleLocalFileManager, mocker
) -> None:
    """Test that the read function fails, raising ParticleFileManagerError when a
    JSONDecodeError is captured.
    """
    mocker.patch("json.load", side_effect=JSONDecodeError("test", "json", 1))
    with pytest.raises(ParticleFileManagerError):
        particle_local_filemanager.get_manifest_schema()


def test_local_filemanager_get_file_os_error(
    particle_local_filemanager: ParticleLocalFileManager, mocker
) -> None:
    """Test that the read function fails, raising ParticleFileManagerError when an
    OSError is captured.
    """
    mocker.patch("json.load", side_effect=OSError("test", "json", 1))
    with pytest.raises(ParticleFileManagerError):
        particle_local_filemanager.get_manifest_schema()


def test_local_filemanager_get_file_invalid_path() -> None:
    """Test that read domain fails and raises ParticleFileManagerError
    exception with invalid file path.
    """
    test_path = ParticleLocalFileManager("./wrongfile.json")
    with pytest.raises(ParticleFileManagerError):
        test_path.get_manifest_schema()


def test_get_remote_file(
    particle_remote_filemanager: ParticleRemoteFileManager,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that the Remote Filemanager get_manifest_file method returns manifest data."""
    caplog.set_level(logging.INFO)

    result = particle_remote_filemanager.get_manifest_file()

    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.games.particle.backends.filemanager"
    )

    # verify basic contents of manifest json
    assert isinstance(result, dict)
    assert result["schemaVersion"]
    assert len(result["channels"]) == 2

    # verify logging
    assert len(records) == 1
    assert records[0].message.startswith("Successfully loaded remote Particle manifest file.")


def test_get_remote_file_empty(
    particle_remote_filemanager: ParticleRemoteFileManager,
) -> None:
    """Test that the RemoteFileManager returns None when the call to GCS returns None."""
    particle_remote_filemanager.gcs_client = MagicMock()
    particle_remote_filemanager.gcs_client.get_file_by_name.return_value = None

    result = particle_remote_filemanager.get_manifest_file()
    assert result is None


def test_get_remote_file_error(
    particle_remote_filemanager: ParticleRemoteFileManager,
) -> None:
    """Test that the RemoteFileManager returns None when the call to GCS fails."""
    particle_remote_filemanager.gcs_client = MagicMock()
    particle_remote_filemanager.gcs_client.get_file_by_name.side_effect = Exception("Test error")

    result = particle_remote_filemanager.get_manifest_file()
    assert result is None
