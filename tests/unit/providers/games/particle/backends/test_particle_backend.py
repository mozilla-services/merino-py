# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle backend."""

import json
import logging
import pytest

from httpx import AsyncClient, Request, Response
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from requests import HTTPError
from typing import Any, cast
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

from merino.configs import settings
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.games.particle.backends.filemanager import ParticleRemoteFileManager
from merino.providers.games.particle.backends.particle import ParticleBackend
from merino.providers.games.particle.backends.utils import GameFile, RemoteChannelEnum

_game_url = settings.games_providers.particle.game_url

# these values don't really matter, as the http calls are mocked
PARTICLE_URL_ROOT = "http://test.com"
PARTICLE_URL_PATH_MANIFEST = "/manifest.v1.json"


# FIXTURES
@pytest.fixture()
def valid_manifest_data():
    """Load mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture()
def valid_manifest_data_json():
    """Load mock response data from the Particle manifest endpoint after being converted to JSON."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return json.load(f)


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="particle_remote_filemanager_parameters")
def fixture_particle_remote_filemanager_parameters(gcs_uploader_mock) -> dict[str, Any]:
    """Define ParticleRemoteFileManager parameters for test."""
    return {
        "gcs_client": gcs_uploader_mock,
        "manifest_file_name": "test_file.json",
        "green_deployment_folder": "green_deployment",
    }


@pytest.fixture(name="particle_remote_filemanager")
def fixture_particle_remote_filemanager(
    particle_remote_filemanager_parameters: dict[str, Any],
) -> ParticleRemoteFileManager:
    """Create a ParticleRemoteFileManager object for test."""
    return ParticleRemoteFileManager(**particle_remote_filemanager_parameters)


@pytest.fixture
def mock_remote_manifest_channel_is_updated():
    """Return mock remote_manifest_channel_is_updated function."""
    with patch(
        "merino.providers.games.particle.backends.particle.remote_manifest_channel_is_updated"
    ) as mock_remote_manifest_channel_is_updated:
        yield mock_remote_manifest_channel_is_updated


@pytest.fixture
def mock_get_files_from_manifest_for_channel():
    """Return mock get_files_from_manifest_for_channel function."""
    with patch(
        "merino.providers.games.particle.backends.particle.get_files_from_manifest_for_channel"
    ) as mock_get_files_from_manifest_for_channel:
        yield mock_get_files_from_manifest_for_channel


@pytest.fixture(name="backend")
def fixture_backend(
    gcs_uploader_mock: GcsUploader,
    mocker: MockerFixture,
    statsd_mock,
    particle_remote_filemanager: ParticleRemoteFileManager,
) -> ParticleBackend:
    """Return a ParticleBackend instance for testing."""
    return ParticleBackend(
        gcs_uploader=gcs_uploader_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        metrics_client=statsd_mock,
        particle_url_root=PARTICLE_URL_ROOT,
        particle_url_path_manifest=PARTICLE_URL_PATH_MANIFEST,
        remote_file_manager=particle_remote_filemanager,
    )


@pytest.fixture
def mock_stage_channel_files(backend):
    """Return a mocked stage_channel_files async function."""
    with patch.object(
        backend, "stage_channel_files", new_callable=AsyncMock
    ) as mock_stage_channel_files:
        yield mock_stage_channel_files


@pytest.fixture
def mock_deploy_channel_files(backend):
    """Return a mocked deploy_channel_files async function."""
    with patch.object(
        backend, "deploy_channel_files", new_callable=AsyncMock
    ) as mock_deploy_channel_files:
        yield mock_deploy_channel_files


@pytest.fixture
def mock_cleanup_old_files_for_channel(backend):
    """Return a mocked cleanup_old_files_for_channel async function."""
    with patch.object(
        backend, "cleanup_old_files_for_channel", new_callable=AsyncMock
    ) as mock_cleanup_old_files_for_channel:
        yield mock_cleanup_old_files_for_channel


@pytest.fixture
def mock_successfully_updated_game_files() -> list[GameFile]:
    """Mock files that have been successfully verified and uploaded."""
    files = [
        GameFile(url="/path/to/file.jpg", sha="1234abcd", content_type="image/jpeg"),
        GameFile(url="/path/to/style.css", sha="5678abcd", content_type="text/css; charset=utf-8"),
    ]

    for f in files:
        f.sha_verified = True
        f.uploaded = True

    return files


@pytest.fixture
def mock_download_remote_file():
    """Return a mock of the download_remote_file function."""
    with patch(
        "merino.providers.games.particle.backends.particle.download_remote_file"
    ) as mock_download_remote_file:
        yield mock_download_remote_file


@pytest.fixture
def mock_upload_file(backend):
    """Return a mocked upload_file method on the remote_file_manager."""
    with patch.object(
        backend.remote_file_manager, "upload_file", new_callable=AsyncMock
    ) as mock_upload_file:
        yield mock_upload_file


@pytest.fixture
def mock_empty_staging_folder(backend):
    """Return a mocked empty_staging_folder method on the remote_file_manager."""
    with patch.object(
        backend.remote_file_manager, "empty_staging_folder", new_callable=AsyncMock
    ) as mock_empty_staging_folder:
        yield mock_empty_staging_folder


@pytest.fixture
def mock_compute_sha():
    """Return a mock of the get_file_sha function."""
    with patch.object(GameFile, "compute_sha") as mock_compute_sha:
        yield mock_compute_sha


@pytest.fixture()
def mock_particle_game_file():
    """Load a sample game file from Particle's server."""
    with open("tests/data/games/particle/image.jpg", "rb") as f:
        return f.read()


# END FIXTURES


@pytest.mark.asyncio
async def test_get_game_url_returns_correct_particle(backend: ParticleBackend) -> None:
    """Test that get_game_url returns the expected game URL value."""
    result = await backend.get_game_url()

    assert result is not None
    assert result.url == _game_url


class TestFetchManifestJson:
    """Tests against fetch_manifest_json"""

    @pytest.mark.asyncio
    async def test_returns_json(self, valid_manifest_data, backend: ParticleBackend) -> None:
        """Test fetching manifest JSON succeeds along happy path."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=valid_manifest_data,
            request=Request(method="GET", url=PARTICLE_URL_ROOT),
        )

        result = await backend.fetch_manifest_json_from_remote()

        # result should be a python object (result of json.loads)
        assert isinstance(result, object)

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_json(
        self, backend: ParticleBackend, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Test fetching invalid manifest JSON returns None."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            # foo below isn't double quoted, so json conversion fails
            content="{foo: 1}",
            request=Request(method="GET", url=PARTICLE_URL_ROOT),
        )

        caplog.set_level(logging.ERROR)

        result = await backend.fetch_manifest_json_from_remote()

        # get error records
        error_records = filter_caplog(
            caplog.records,
            "merino.providers.games.particle.backends.particle",
        )

        # verify result is None and expected error was logged
        assert result is None
        assert len(error_records) == 1
        assert "JSON error when converting Particle response" == error_records[0].message

    @pytest.mark.asyncio
    async def test_returns_none_for_http_error(
        self, backend: ParticleBackend, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Test fetching invalid manifest JSON returns None."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=500, request=Request(method="GET", url=PARTICLE_URL_ROOT)
        )

        caplog.set_level(logging.ERROR)

        result = await backend.fetch_manifest_json_from_remote()

        # get error records
        error_records = filter_caplog(
            caplog.records,
            "merino.providers.games.particle.backends.particle",
        )

        # make sure result is None and expected error has been logged
        assert result is None
        assert len(error_records) == 1
        assert "HTTP error when fetching Particle manifest" in error_records[0].message


class TestUpdateChannelFiles:
    """Tests against update_channel_files"""

    def setup_method(self):
        """Reset the list of GameFiles before each test."""
        self.mock_game_files = [
            GameFile(url="path/to/file.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(
                url="path/to/style.css", sha="5678abcd", content_type="text/css; charset=utf-8"
            ),
        ]

    test_params = [
        RemoteChannelEnum.RUNTIME,
        RemoteChannelEnum.PUZZLE,
    ]

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_is_updated_with_version_update_and_successfully_staged_files(
        self,
        backend,
        valid_manifest_data_json,
        mock_remote_manifest_channel_is_updated,
        mock_stage_channel_files,
        mock_deploy_channel_files,
        mock_cleanup_old_files_for_channel,
        mock_successfully_updated_game_files,
        mock_get_files_from_manifest_for_channel,
        channel,
    ):
        """Test that channel is marked as updated if manifest versions mismatch, channel files are found, and staging deployment was successful (happy path)."""
        # set up mocks for happy path
        mock_remote_manifest_channel_is_updated.return_value = True
        mock_get_files_from_manifest_for_channel.return_value = self.mock_game_files
        mock_stage_channel_files.side_effect = [(True, mock_successfully_updated_game_files)]
        mock_deploy_channel_files.side_effect = [True]

        assert await backend.update_channel_files(
            valid_manifest_data_json, valid_manifest_data_json, channel
        )

        # ensure all inner functions were called as expected
        mock_remote_manifest_channel_is_updated.assert_called_once()
        mock_get_files_from_manifest_for_channel.assert_called_once()
        mock_stage_channel_files.assert_awaited_once()
        mock_deploy_channel_files.assert_awaited_once()
        mock_cleanup_old_files_for_channel.assert_awaited_once()

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_not_updated_if_manifest_versions_match(
        self,
        backend,
        valid_manifest_data_json,
        mock_remote_manifest_channel_is_updated,
        mock_stage_channel_files,
        mock_get_files_from_manifest_for_channel,
        mock_deploy_channel_files,
        mock_cleanup_old_files_for_channel,
        channel,
    ):
        """Test that channel is not marked as updated if manifest versions match."""
        # force manifest to not signal it is updated
        mock_remote_manifest_channel_is_updated.return_value = False

        assert not await backend.update_channel_files(
            valid_manifest_data_json, valid_manifest_data_json, channel
        )

        # ensure only expected function was called
        mock_remote_manifest_channel_is_updated.assert_called_once()

        # if the manifest doesn't need an update, then no further processing should happen
        mock_get_files_from_manifest_for_channel.assert_not_called()
        mock_stage_channel_files.assert_not_awaited()
        mock_deploy_channel_files.assert_not_awaited()
        mock_cleanup_old_files_for_channel.assert_not_awaited()

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_not_updated_if_no_channel_files_found(
        self,
        backend,
        valid_manifest_data_json,
        mock_remote_manifest_channel_is_updated,
        mock_stage_channel_files,
        mock_get_files_from_manifest_for_channel,
        mock_deploy_channel_files,
        mock_cleanup_old_files_for_channel,
        channel,
    ):
        """Test that channel is not marked as updated if no files were found for the channel."""
        mock_remote_manifest_channel_is_updated.return_value = True

        # force no files to be found for the channel
        mock_get_files_from_manifest_for_channel.return_value = []

        assert not await backend.update_channel_files(
            valid_manifest_data_json, valid_manifest_data_json, channel
        )

        mock_remote_manifest_channel_is_updated.assert_called_once()
        mock_get_files_from_manifest_for_channel.assert_called_once()

        # staging and deploying should not be attempted
        mock_stage_channel_files.assert_not_awaited()
        mock_deploy_channel_files.assert_not_awaited()
        mock_cleanup_old_files_for_channel.assert_not_awaited()

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_not_updated_with_unsuccessful_staging(
        self,
        backend,
        valid_manifest_data_json,
        mock_remote_manifest_channel_is_updated,
        mock_stage_channel_files,
        mock_get_files_from_manifest_for_channel,
        mock_deploy_channel_files,
        mock_cleanup_old_files_for_channel,
        channel,
    ):
        """Test that channel is not marked as updated if staging call results in files not successfully verified and uploaded."""
        mock_remote_manifest_channel_is_updated.return_value = True
        mock_get_files_from_manifest_for_channel.return_value = self.mock_game_files
        # force staging to be a failure
        mock_stage_channel_files.side_effect = [(False, self.mock_game_files)]

        assert not await backend.update_channel_files(
            valid_manifest_data_json, valid_manifest_data_json, channel
        )

        mock_remote_manifest_channel_is_updated.assert_called_once()
        mock_get_files_from_manifest_for_channel.assert_called_once()
        mock_stage_channel_files.assert_awaited_once()

        # deploy should not be attempted
        mock_deploy_channel_files.assert_not_awaited()
        mock_cleanup_old_files_for_channel.assert_not_awaited()

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_not_updated_with_unsuccessful_deployment(
        self,
        backend,
        valid_manifest_data_json,
        mock_remote_manifest_channel_is_updated,
        mock_stage_channel_files,
        mock_get_files_from_manifest_for_channel,
        mock_deploy_channel_files,
        mock_cleanup_old_files_for_channel,
        channel,
    ):
        """Test that channel is not marked as updated if deployment fails."""
        mock_remote_manifest_channel_is_updated.return_value = True
        mock_get_files_from_manifest_for_channel.return_value = self.mock_game_files
        # staging is a success
        mock_stage_channel_files.side_effect = [(True, self.mock_game_files)]
        # force deployment to be a failure
        mock_deploy_channel_files.side_effect = [False]

        assert not await backend.update_channel_files(
            valid_manifest_data_json, valid_manifest_data_json, channel
        )

        # most inner functions should have been called
        mock_remote_manifest_channel_is_updated.assert_called_once()
        mock_get_files_from_manifest_for_channel.assert_called_once()
        mock_stage_channel_files.assert_awaited_once()
        mock_deploy_channel_files.assert_awaited_once()

        mock_cleanup_old_files_for_channel.assert_not_awaited()


class TestStageChannelFiles:
    """Tests against the stage_channel_files function."""

    # manually computed sha of file above
    MOCK_PARTICLE_GAME_FILE_SHA = (
        "57120c40b8bd7d84b861751958c19b40343b14fe028ae7f9a1e7251560c6817a"
    )

    def setup_method(self):
        """Reset the list of GameFiles before each test."""
        self.mock_game_files = [
            GameFile(url="path/to/file.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(
                url="path/to/style.css", sha="5678abcd", content_type="text/css; charset=utf-8"
            ),
        ]

    @pytest.mark.asyncio
    async def test_success(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Test success scenario where all files are successfully downloaded, have validated SHAs, and are uploaded to GCS."""
        # ensure both file downloads are successsful
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
            mock.DEFAULT,
        ]

        # match the fake shas above
        mock_compute_sha.side_effect = ["1234abcd", "5678abcd"]

        # ensure both file uploads are successful
        mock_upload_file.side_effect = ["green/path/to/file.jpg", "green/path/to/style.css"]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert success

        # these should be called once for each game file
        assert mock_download_remote_file.call_count == len(self.mock_game_files)
        assert mock_compute_sha.call_count == len(self.mock_game_files)
        assert mock_upload_file.call_count == len(self.mock_game_files)

        # as all uploads were successful, the staging folder should not be emptied
        assert mock_empty_staging_folder.call_count == 0

        # all game files should be marked as verified and uploaded
        assert all(f.sha_verified and f.uploaded for f in files)

        # both files should have the GCS staging name set
        assert files[0].gcs_staging_name == "green/path/to/file.jpg"
        assert files[1].gcs_staging_name == "green/path/to/style.css"

    @pytest.mark.asyncio
    async def test_first_file_download_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Verify behavior when the first file download fails with an HTTPError."""
        mock_download_remote_file.side_effect = [
            HTTPError("forced error"),
            mock.DEFAULT,
        ]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # only the first call to download_remote_file should happen, as it is
        # forced to raise above
        assert mock_download_remote_file.call_count == 1

        # we should never get to sha validation or uploading, as processing should stop when
        # hitting the download_remote_file exception
        assert mock_compute_sha.call_count == 0
        assert mock_upload_file.call_count == 0

        # since no files were successfully uploaded, we don't need to empty the staging folder
        assert mock_empty_staging_folder.call_count == 0

        # no game files should be marked as verified
        assert not any(f.sha_verified or f.uploaded for f in files)

    @pytest.mark.asyncio
    async def test_second_file_download_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Test behavior when second file download fails with an HTTPError."""
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
            HTTPError("forced error"),
        ]

        # match the fake shas above
        mock_compute_sha.side_effect = ["1234abcd", "5678abcd"]

        # ensure first file upload is successful (second shouldn't happen)
        mock_upload_file.side_effect = ["green/file.jpg"]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # both files should be attempted to be downloaded
        assert mock_download_remote_file.call_count == 2

        # only the first file, downloaded successfully, should have its SHA verified
        # and be uploaded
        assert mock_compute_sha.call_count == 1
        assert mock_upload_file.call_count == 1

        # since only one of two files was successfully uploaded, we should empty the
        # staging folder
        mock_empty_staging_folder.assert_awaited_once()

        # no game files should be marked as verified
        assert files[0].sha_verified
        assert files[0].uploaded
        assert files[0].gcs_staging_name == "green/file.jpg"
        assert not files[1].sha_verified
        assert not files[1].uploaded

    @pytest.mark.asyncio
    async def test_first_sha_validation_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Verify behavior when the first SHA validation fails."""
        # only the first download should happen
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
        ]

        # only the first SHA comparison should happen
        mock_compute_sha.side_effect = ["SHAntValidate"]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # only the first file should be downloaded, as a SHA failure halts all
        # further processing
        assert mock_download_remote_file.call_count == 1

        # only one SHA should be validated (and failed)
        assert mock_compute_sha.call_count == 1

        # no files should be uploaded
        assert mock_upload_file.call_count == 0

        # since no files were successfully uploaded, we don't need to empty the staging folder
        assert mock_empty_staging_folder.call_count == 0

        # no game files should be marked as verified
        assert not any(f.sha_verified or f.uploaded for f in files)

    @pytest.mark.asyncio
    async def test_second_sha_validation_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Verify behavior when the second SHA validation fails."""
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
            mock.DEFAULT,
        ]

        # match the fake shas above
        mock_compute_sha.side_effect = ["1234abcd", "SHAntValidate"]

        # ensure first file upload is successful (second shouldn't happen)
        mock_upload_file.side_effect = ["green/file.jpg"]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # both files should be downloaded
        assert mock_download_remote_file.call_count == 2

        # both SHAs should be validated
        assert mock_compute_sha.call_count == 2

        # only the first file should be uploaded
        assert mock_upload_file.call_count == 1

        # since one file was uploaded, we should empty the staging folder
        assert mock_empty_staging_folder.call_count == 1

        assert files[0].sha_verified
        assert files[0].uploaded
        assert files[0].gcs_staging_name == "green/file.jpg"
        assert not files[1].sha_verified
        assert not files[1].uploaded

    @pytest.mark.asyncio
    async def test_first_file_upload_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Verify behavior when the first file upload fails."""
        # only the first download should happen
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
        ]

        # only the first SHA comparison should happen
        mock_compute_sha.side_effect = ["1234abcd"]

        # ensure both file uploads are successful
        mock_upload_file.side_effect = [""]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # only the first file should be downloaded, as a SHA failure halts all
        # further processing
        assert mock_download_remote_file.call_count == 1

        # only one SHA should be validated
        assert mock_compute_sha.call_count == 1

        # only the first file should be uploaded
        assert mock_upload_file.call_count == 1

        # since no files were successfully uploaded, we don't need to empty the staging folder
        assert mock_empty_staging_folder.call_count == 0

        # no game files should be marked as verified
        assert not any(f.uploaded for f in files)

    @pytest.mark.asyncio
    async def test_second_file_upload_fails(
        self,
        backend,
        mock_download_remote_file,
        mock_compute_sha,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Verify behavior when the second file upload fails."""
        # both downloads should happen
        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
            mock.DEFAULT,
        ]

        # both SHA comparisons should happen
        mock_compute_sha.side_effect = ["1234abcd", "5678abcd"]

        # ensure both file uploads are successful
        mock_upload_file.side_effect = ["green_deploymen/file.jpg", ""]

        success, files = await backend.stage_channel_files(self.mock_game_files)

        assert not success

        # both files should be downloaded
        assert mock_download_remote_file.call_count == 2

        # both shas should be validated
        assert mock_compute_sha.call_count == 2

        # both files should be uploaded
        assert mock_upload_file.call_count == 2

        # since one file was uploaded, we should empty the staging folder
        assert mock_empty_staging_folder.call_count == 1

        # no game files should be marked as verified
        assert files[0].uploaded

    @pytest.mark.asyncio
    @patch("requests.get")
    async def test_file_download_to_tempdir_and_real_sha_check(
        self,
        mock_get,
        backend,
        mock_particle_game_file,
        mock_upload_file,
        mock_empty_staging_folder,
    ):
        """Test actual SHA validation functionality."""
        # actual binary file data from a local test image file
        mock_get.return_value.content = mock_particle_game_file

        # ensure the upload succeeds
        mock_upload_file.side_effect = ["green/path/to/file.jpg"]

        mock_game_files = [
            GameFile(
                url="path/to/file.jpg",
                sha=self.MOCK_PARTICLE_GAME_FILE_SHA,
                content_type="image/jpeg",
            ),
        ]

        # should be true as download and sha check are successful
        success, files = await backend.stage_channel_files(mock_game_files)

        assert success

        # explicitly verify the sha computed in the call above matches the
        # expected manually computed sha
        assert files[0].sha_computed == self.MOCK_PARTICLE_GAME_FILE_SHA

        # as all succeeded, we should not empty the staging folder
        assert mock_empty_staging_folder.call_count == 0

        # file should be marked as verified and uploaded
        assert all(f.sha_verified and f.uploaded for f in files)

        # file should have a GCS name
        assert files[0].gcs_staging_name == "green/path/to/file.jpg"


class TestDeployChannelFiles:
    """Tests against the deploy_channel_files method."""

    def setup_method(self):
        """Reset the list of GameFiles before each test."""
        self.mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd", content_type="image/jpeg"),
            GameFile(
                url="/path/to/style.css", sha="5678abcd", content_type="text/css; charset=utf-8"
            ),
        ]

    test_params = [[True, True], [True, False], [False, True]]

    @pytest.mark.parametrize("deploy_success, upload_manifest_success", test_params)
    @pytest.mark.asyncio
    async def test_success_and_failure_scenarios(
        self, deploy_success, upload_manifest_success, backend, valid_manifest_data_json
    ):
        """Verify success/failure behavior given different sub-function results."""
        with (
            patch.object(
                backend.remote_file_manager, "deploy_staged_files", new_callable=AsyncMock
            ) as mock_deploy,
            patch.object(
                backend.remote_file_manager, "upload_manifest", new_callable=AsyncMock
            ) as mock_upload_manifest,
        ):
            mock_deploy.side_effect = [deploy_success]
            mock_upload_manifest.side_effect = [upload_manifest_success]

            success = await backend.deploy_channel_files(
                self.mock_game_files, valid_manifest_data_json
            )

            assert success == (deploy_success and upload_manifest_success)

            mock_deploy.assert_awaited_once_with(self.mock_game_files)

            if deploy_success:
                mock_upload_manifest.assert_awaited_once_with(valid_manifest_data_json)
