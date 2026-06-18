# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle filemanager module."""

import json
import logging
import orjson
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
from unittest import mock
from unittest.mock import call, MagicMock, patch

from merino.configs import settings
from merino.providers.games.particle.backends.filemanager import (
    ParticleFileManagerError,
    ParticleLocalFileManager,
    ParticleRemoteFileManager,
)
from merino.providers.games.particle.backends.utils import GameFile
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


@pytest.fixture(name="remote_manifest_json")
def fixture_remote_manifest_json():
    """Load manifest data from local file into JSON - simulates data downloaed from Particle endpoint and converted to JSON."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return json.load(f)


@pytest.fixture(name="gcs_manifest_string")
def fixture_gcs_manifest_string():
    """Load manifest data from local file - simulates string returned from GCS."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="manifest_gcs_blob_mock")
def fixture_gcs_manifest_blob(mocker: MockerFixture, gcs_manifest_string: str) -> Any:
    """Create a GCS Blob mock object for testing."""
    mock_blob = mocker.MagicMock(spec=Blob)
    mock_blob.name = "runtime-manifest.v1.json"
    mock_blob.download_as_text.return_value = gcs_manifest_string

    return mock_blob


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock(manifest_gcs_blob_mock) -> GcsUploader:
    """Return a mock GcsUploader."""
    mock = MagicMock(spec=GcsUploader)
    mock.get_file_by_name.return_value = manifest_gcs_blob_mock

    return mock


@pytest.fixture(name="remote_filemanager_parameters")
def fixture_remote_filemanager_parameters(gcs_uploader_mock) -> dict[str, Any]:
    """Define ParticleRemoteFileManager parameters for test."""
    return {
        "gcs_client": gcs_uploader_mock,
        "manifest_file_name": "test_manifest.json",
        "green_deployment_folder": "green_deployment",
    }


@pytest.fixture(name="remote_filemanager")
def fixture_remote_filemanager(
    remote_filemanager_parameters: dict[str, Any],
) -> ParticleRemoteFileManager:
    """Create a ParticleRemoteFileManager object for test."""
    with (
        patch("google.auth.default") as mock_auth_default,
    ):
        creds = AnonymousCredentials()  # type: ignore
        mock_auth_default.return_value = (creds, "test-project")
        return ParticleRemoteFileManager(**remote_filemanager_parameters)


class TestRemoteFileManager:
    """Tests against Particle RemoteFileManager."""

    def test_get_manifest_file(
        self,
        remote_filemanager: ParticleRemoteFileManager,
        caplog: LogCaptureFixture,
        filter_caplog: FilterCaplogFixture,
    ) -> None:
        """Test that the Remote Filemanager get_manifest_file method returns manifest data."""
        caplog.set_level(logging.INFO)

        result = remote_filemanager.get_manifest_file()

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
        remote_filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager returns None when the call to GCS returns None."""
        remote_filemanager.gcs_client = MagicMock()
        remote_filemanager.gcs_client.get_file_by_name.return_value = None

        assert remote_filemanager.get_manifest_file() is None

    def test_get_manifest_file_invalid_json(
        self,
        remote_filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager raises when the call to GCS returns invalid JSON."""
        remote_filemanager.gcs_client = MagicMock()
        remote_filemanager.gcs_client.get_file_by_name.return_value = "invalid json"

        with pytest.raises(ParticleFileManagerError):
            remote_filemanager.get_manifest_file()

    def test_get_manifest_file_error(
        self,
        remote_filemanager: ParticleRemoteFileManager,
    ) -> None:
        """Test that the RemoteFileManager raises when the call to GCS fails."""
        remote_filemanager.gcs_client = MagicMock()
        remote_filemanager.gcs_client.get_file_by_name.side_effect = Exception("Test error")

        with pytest.raises(ParticleFileManagerError):
            remote_filemanager.get_manifest_file()


class TestRemoteFileManagerEmptyStagingFolder:
    """Tests against the empty_staging_folder function of ParticleRemoteFileManager."""

    @pytest.mark.asyncio
    async def test_success(self, remote_filemanager):
        """Verify the call succeeds."""
        # simulate a partially staged fileset
        files: list[GameFile] = [
            GameFile(url="https://test.com/test.html", sha="1234abcd", content_type="text/html"),
            GameFile(url="https://test.com/test.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(url="https://test.com/test.png", sha="1234abcd", content_type="image/png"),
            GameFile(
                url="https://test.com/test.json", sha="1234abcd", content_type="application/json"
            ),
        ]

        # only some of the files were successfully uploaded
        files[0].uploaded = True
        files[0].gcs_staging_name = "green/test.html"
        files[1].uploaded = True
        files[1].gcs_staging_name = "green/test.jpg"
        files[3].uploaded = True
        files[3].gcs_staging_name = "green/test.json"

        with patch.object(remote_filemanager.gcs_client, "delete_file_by_name") as mock_delete:
            await remote_filemanager.empty_staging_folder(files)

            assert mock_delete.call_count == 3

    @pytest.mark.asyncio
    async def test_filters_files_correctly(self, remote_filemanager):
        """Verify the call succeeds and filters files correctly."""
        # simulate a partially staged fileset
        files: list[GameFile] = [
            GameFile(url="https://test.com/test.html", sha="1234abcd", content_type="text/html"),
            GameFile(url="https://test.com/test.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(url="https://test.com/test.png", sha="1234abcd", content_type="image/png"),
            GameFile(
                url="https://test.com/test.json", sha="1234abcd", content_type="application/json"
            ),
        ]

        # only some of the files were successfully uploaded
        files[0].uploaded = True
        files[0].gcs_staging_name = "green/test.html"
        # this file is in an invalid state - no gcs_staging_name set, so it
        # shouldn't be processed
        files[1].uploaded = True
        files[3].uploaded = True
        files[3].gcs_staging_name = "green/test.json"

        with patch.object(remote_filemanager.gcs_client, "delete_file_by_name") as mock_delete:
            await remote_filemanager.empty_staging_folder(files)

            # should have only been called twice
            assert mock_delete.call_count == 2

            # should only have been called with files with a gcs_staging_name
            calls = [call("green/test.html"), call("green/test.json")]

            mock_delete.assert_has_calls(calls)

    @pytest.mark.asyncio
    async def test_failure(self, remote_filemanager, mocker):
        """Verify sentry is called when the GCS client captures an exception."""
        # simulate a partially staged fileset
        files: list[GameFile] = [
            GameFile(url="https://test.com/test.html", sha="1234abcd", content_type="text/html"),
            GameFile(url="https://test.com/test.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(url="https://test.com/test.png", sha="1234abcd", content_type="image/png"),
            GameFile(
                url="https://test.com/test.json", sha="1234abcd", content_type="application/json"
            ),
        ]

        # only some of the files were successfully uploaded
        files[0].uploaded = True
        files[0].gcs_staging_name = "green/test.html"
        files[1].uploaded = True
        files[1].gcs_staging_name = "green/test.jpg"
        files[3].uploaded = True
        files[3].gcs_staging_name = "green/test.json"

        sentry_capture = mocker.patch(
            "merino.providers.games.particle.backends.filemanager.sentry_sdk.capture_exception"
        )

        with patch.object(remote_filemanager.gcs_client, "delete_file_by_name") as mock_delete:
            mock_delete.side_effect = [
                Exception("first delete fails"),
                mock.DEFAULT,
                Exception("third delete fails"),
            ]

            await remote_filemanager.empty_staging_folder(files)

            # each file should be attempted to be deleted
            assert mock_delete.call_count == 3

            # two of the deletes should fail and send to sentry
            assert sentry_capture.call_count == 2


class TestRemoteFileManagerDeployStagedFiles:
    """Tests against the deploy_staged_files function."""

    @pytest.mark.asyncio
    async def test_success(self, remote_filemanager):
        """Test success scenario."""
        # simulate a staged fileset
        files: list[GameFile] = [
            GameFile(url="runtime/test.html", sha="1234abcd", content_type="text/html"),
            GameFile(url="assets/test.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(url="assets/test.png", sha="1234abcd", content_type="image/png"),
            GameFile(url="generated/test.json", sha="1234abcd", content_type="application/json"),
        ]

        # finish simulating a staged fileset
        files[0].uploaded = True
        files[0].gcs_staging_name = "green/runtime/test.html"
        files[1].uploaded = True
        files[1].gcs_staging_name = "green/assets/test.jpg"
        files[2].uploaded = True
        files[2].gcs_staging_name = "green/assets/test.png"
        files[3].uploaded = True
        files[3].gcs_staging_name = "green/generated/test.json"

        with patch.object(remote_filemanager.gcs_client, "move_file") as mock_move_file:
            assert await remote_filemanager.deploy_staged_files(files)

            assert mock_move_file.call_count == 4

            # should have been called for each file staged above
            # note the check for renaming 'runtime/test.html' to 'index.html'
            calls = [
                call("green/runtime/test.html", "index.html"),
                call("green/assets/test.jpg", "assets/test.jpg"),
                call("green/assets/test.png", "assets/test.png"),
                call("green/generated/test.json", "generated/test.json"),
            ]

            mock_move_file.assert_has_calls(calls)

    @pytest.mark.asyncio
    async def test_failure(self, remote_filemanager, mocker):
        """Verify sentry is called when the GCS client captures an exception."""
        # simulate a staged fileset
        files: list[GameFile] = [
            GameFile(url="runtime/test.html", sha="1234abcd", content_type="text/html"),
            GameFile(url="assets/test.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(url="assets/test.png", sha="1234abcd", content_type="image/png"),
            GameFile(url="generated/test.json", sha="1234abcd", content_type="application/json"),
        ]

        # finish simulating a staged fileset
        files[0].uploaded = True
        files[0].gcs_staging_name = "green/runtime/test.html"
        files[1].uploaded = True
        files[1].gcs_staging_name = "green/assets/test.jpg"
        files[2].uploaded = True
        files[2].gcs_staging_name = "green/assets/test.png"
        files[3].uploaded = True
        files[3].gcs_staging_name = "green/generated/test.json"

        sentry_capture = mocker.patch(
            "merino.providers.games.particle.backends.filemanager.sentry_sdk.capture_exception"
        )

        with patch.object(remote_filemanager.gcs_client, "move_file") as mock_move_file:
            mock_move_file.side_effect = [
                Exception("first move fails"),
                mock.DEFAULT,
                Exception("third move fails"),
                mock.DEFAULT,
            ]

            assert not await remote_filemanager.deploy_staged_files(files)

            # each file should be attempted to be moved
            assert mock_move_file.call_count == 4

            # two of the moves should fail and send to sentry
            assert sentry_capture.call_count == 2


class TestRemoteFileManagerUploadManifest:
    """Tests against the upload_manifest function."""

    @pytest.mark.asyncio
    async def test_success(self, remote_filemanager, remote_manifest_json):
        """Verify success scenario."""
        with patch.object(remote_filemanager.gcs_client, "upload_content") as mock_upload:
            assert await remote_filemanager.upload_manifest(remote_manifest_json)

            mock_upload.assert_called_once_with(
                content=orjson.dumps(remote_manifest_json),
                destination_name=remote_filemanager.manifest_file_name,
                content_type="application/json",
                forced_upload=True,
            )

    @pytest.mark.asyncio
    async def test_failure(self, remote_filemanager, remote_manifest_json, mocker):
        """Verify failure scenario."""
        sentry_capture = mocker.patch(
            "merino.providers.games.particle.backends.filemanager.sentry_sdk.capture_exception"
        )

        with patch.object(remote_filemanager.gcs_client, "upload_content") as mock_upload:
            mock_upload.return_value = Blob(
                name=remote_filemanager.manifest_file_name, bucket=MagicMock()
            )

            assert not await remote_filemanager.upload_manifest(remote_manifest_json)

            mock_upload.assert_called_once_with(
                content=orjson.dumps(remote_manifest_json),
                destination_name=remote_filemanager.manifest_file_name,
                content_type="application/json",
                forced_upload=True,
            )

            assert sentry_capture.call_count == 1


class TestRemoteFileManagerDeleteFile:
    """Tests against the delete_file method of ParticleRemoteFileManager."""

    @pytest.mark.asyncio
    async def test_success(self, remote_filemanager):
        """Verify success behavior."""
        with patch.object(remote_filemanager.gcs_client, "delete_file_by_name") as mock_delete:
            await remote_filemanager.delete_file("assets/index.js")

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure(self, remote_filemanager, mocker):
        """Verify failure behavior."""
        sentry_capture = mocker.patch(
            "merino.providers.games.particle.backends.filemanager.sentry_sdk.capture_exception"
        )

        with patch.object(remote_filemanager.gcs_client, "delete_file_by_name") as mock_delete:
            mock_delete.side_effect = [Exception("forced error")]

            await remote_filemanager.delete_file("assets/index.js")

            sentry_capture.assert_called_once()

            mock_delete.assert_called_once()
