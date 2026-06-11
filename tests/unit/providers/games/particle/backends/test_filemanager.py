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


class TestLocalFileManager:
    """Tests against the Particle LocalFileManager"""

    @pytest.fixture(name="filemanager_parameters")
    def fixture_filemanager_parameters(self) -> dict[str, Any]:
        """Define ParticleLocalFileManager parameters for test."""
        return {
            "static_manifest_schema_file_path": settings.games_providers.particle.manifest_schema_file_path
        }

    @pytest.fixture(name="filemanager")
    def fixture_particle_local_filemanager(
        self,
        filemanager_parameters: dict[str, Any],
    ) -> ParticleLocalFileManager:
        """Create a ParticleLocalFileManager object for test."""
        return ParticleLocalFileManager(**filemanager_parameters)

    def test_file_exists(self) -> None:
        """Test that the Particle manifest schema file exists locally"""
        assert os.path.exists(settings.games_providers.particle.manifest_schema_file_path)

    def test_get_file(self, filemanager: ParticleLocalFileManager) -> None:
        """Test that the JSON file containing the manifest schema can be processed"""
        schema = filemanager.get_manifest_schema()
        assert schema["title"] == "Client Runtime Manifest v1"
        assert len(schema["properties"]["channels"]["properties"]) == 2

    def test_get_file_json_decode_error(
        self, filemanager: ParticleLocalFileManager, mocker
    ) -> None:
        """Test that the read function fails, raising ParticleFileManagerError when a
        JSONDecodeError is captured.
        """
        mocker.patch("json.load", side_effect=JSONDecodeError("test", "json", 1))
        with pytest.raises(ParticleFileManagerError):
            filemanager.get_manifest_schema()

    def test_get_file_os_error(self, filemanager: ParticleLocalFileManager, mocker) -> None:
        """Test that the read function fails, raising ParticleFileManagerError when an
        OSError is captured.
        """
        mocker.patch("json.load", side_effect=OSError("test", "json", 1))
        with pytest.raises(ParticleFileManagerError):
            filemanager.get_manifest_schema()

    def test_get_file_invalid_path(self) -> None:
        """Test that read domain fails and raises ParticleFileManagerError
        exception with invalid file path.
        """
        test_path = ParticleLocalFileManager("./wrongfile.json")
        with pytest.raises(ParticleFileManagerError):
            test_path.get_manifest_schema()


class TestRemoteFileManager:
    """Tests against Particle RemoteFileManager"""

    @pytest.fixture(name="manifest_json")
    def fixture_manifest_json(self):
        """Load manifest data from local file"""
        with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
            return f.read()

    @pytest.fixture(name="manifest_gcs_blob_mock")
    def fixture_gcs_manifest_blob(self, mocker: MockerFixture, manifest_json: str) -> Any:
        """Create a GCS Blob mock object for testing."""
        mock_blob = mocker.MagicMock(spec=Blob)
        mock_blob.name = "runtime-manifest.v1.json"
        mock_blob.download_as_text.return_value = manifest_json

        return mock_blob

    @pytest.fixture(name="gcs_uploader_mock")
    def fixture_gcs_uploader_mock(self, manifest_gcs_blob_mock) -> GcsUploader:
        """Return a mock GcsUploader."""
        mock = MagicMock(spec=GcsUploader)
        mock.get_file_by_name.return_value = manifest_gcs_blob_mock

        return mock

    @pytest.fixture(name="filemanager_parameters")
    def fixture_filemanager_parameters(self, gcs_uploader_mock) -> dict[str, Any]:
        """Define ParticleRemoteFileManager parameters for test."""
        return {
            "gcs_client": gcs_uploader_mock,
            "manifest_file_name": "test_manifest.json",
            "green_deployment_folder": "green_deployment",
        }

    @pytest.fixture(name="filemanager")
    def fixture_particle_remote_filemanager(
        self,
        filemanager_parameters: dict[str, Any],
    ) -> ParticleRemoteFileManager:
        """Create a ParticleRemoteFileManager object for test."""
        with (
            patch("google.auth.default") as mock_auth_default,
        ):
            creds = AnonymousCredentials()  # type: ignore
            mock_auth_default.return_value = (creds, "test-project")
            return ParticleRemoteFileManager(**filemanager_parameters)

    def test_get_manifest_file(
        self,
        filemanager: ParticleRemoteFileManager,
        caplog: LogCaptureFixture,
        filter_caplog: FilterCaplogFixture,
    ) -> None:
        """Test that the Remote Filemanager get_manifest_file method returns manifest data."""
        caplog.set_level(logging.INFO)

        result = filemanager.get_manifest_file()

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

    def test_get_manifest_file_empty(
        self,
        filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager raises when the call to GCS returns None."""
        filemanager.gcs_client = MagicMock()
        filemanager.gcs_client.get_file_by_name.return_value = None

        with pytest.raises(ParticleFileManagerError):
            filemanager.get_manifest_file()

    def test_get_manifest_file_invalid_json(
        self,
        filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager raises when the call to GCS returns invalid JSON."""
        filemanager.gcs_client = MagicMock()
        filemanager.gcs_client.get_file_by_name.return_value = "invalid json"

        with pytest.raises(ParticleFileManagerError):
            filemanager.get_manifest_file()

    def test_get_manifest_file_error(
        self,
        filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager raises when the call to GCS fails."""
        filemanager.gcs_client = MagicMock()
        filemanager.gcs_client.get_file_by_name.side_effect = Exception("Test error")

        with pytest.raises(ParticleFileManagerError):
            filemanager.get_manifest_file()

    @pytest.mark.asyncio
    async def test_empty_staging_folder(self, filemanager):
        """Stub test."""
        assert await filemanager.empty_staging_folder()
