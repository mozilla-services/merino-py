# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle backend utils."""

import json
import logging
import pytest

from contextlib import nullcontext as does_not_raise
from pydantic import Json
from pytest import LogCaptureFixture
from typing import Any
from unittest import mock
from unittest.mock import patch
from urllib.error import ContentTooShortError

from merino.configs import settings
from merino.providers.games.particle.backends.errors import ParticleManifestValidationError
from merino.providers.games.particle.backends.utils import (
    GameFile,
    get_remote_files_and_shas_for_channel,
    process_remote_fileset_for_channel,
    RemoteChannelEnum,
    remote_manifest_channel_is_updated,
    update_channel_files,
    validate_manifest_schema_version,
    validate_manifest_against_schema,
)

_manifest_schema_version = settings.games_providers.particle.manifest_schema_version


# BEGIN FIXTURES
@pytest.fixture()
def valid_manifest_data():
    """Load mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return json.load(f)


@pytest.fixture()
def valid_manifest_data_remote_updated():
    """Load mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/runtime-manifest-remote-updated.v1.json") as f:
        return json.load(f)


@pytest.fixture()
def invalid_manifest_data():
    """Load invalid mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/invalid-runtime-manifest.v1.json") as f:
        return json.load(f)


@pytest.fixture()
def manifest_schema_data():
    """Retrieve manifest schema JSON."""
    with open("tests/data/games/particle/manifest-validation-schema.json") as f:
        return json.load(f)


@pytest.fixture
def mock_remote_manifest_channel_is_updated():
    """Return mock remote_manifest_channel_is_updated function."""
    with patch(
        "merino.providers.games.particle.backends.utils.remote_manifest_channel_is_updated"
    ) as mock_remote_manifest_channel_is_updated:
        yield mock_remote_manifest_channel_is_updated


@pytest.fixture
def mock_get_remote_files_and_shas_for_channel():
    """Return mock get_remote_files_and_shas_for_channel function."""
    with patch(
        "merino.providers.games.particle.backends.utils.get_remote_files_and_shas_for_channel"
    ) as mock_get_remote_files_and_shas_for_channel:
        yield mock_get_remote_files_and_shas_for_channel


@pytest.fixture
def mock_download_remote_file():
    """Return a mock of the download_remote_file function."""
    with patch(
        "merino.providers.games.particle.backends.utils.download_remote_file"
    ) as mock_download_remote_file:
        yield mock_download_remote_file


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


# manually computed sha of file above
MOCK_PARTICLE_GAME_FILE_SHA = "57120c40b8bd7d84b861751958c19b40343b14fe028ae7f9a1e7251560c6817a"


# END FIXTURES


class TestValidateManifestSchemaVersion:
    """Tests against validate_manifest_schema_version"""

    def test_does_not_raise_with_valid_json(self, valid_manifest_data):
        """Verify valid JSON results in no exception raised."""
        with does_not_raise():
            validate_manifest_schema_version(valid_manifest_data, _manifest_schema_version)

    def test_raises_with_invalid_json(self, caplog: LogCaptureFixture, filter_caplog: Any):
        """Verify invalid JSON raises an exception."""
        caplog.set_level(logging.ERROR)

        with pytest.raises(Exception):
            validate_manifest_schema_version("Not valid JSON", _manifest_schema_version)

            # get error records
            error_records = filter_caplog(
                caplog.records,
                "merino.providers.games.particle.backends.utils",
            )

            # verify expected error was logged
            assert len(error_records) == 1
            assert (
                "JSON error retrieving 'schemaVersion' from manifest JSON."
                == error_records[0].message
            )

    def test_raises_with_invalid_schema_version(
        self, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Verify invalid schema version raises an exception."""
        with pytest.raises(Exception):
            validate_manifest_schema_version(
                json.loads('{"schemaVersion": 2}'), _manifest_schema_version
            )

        # get error records
        error_records = filter_caplog(
            caplog.records,
            "merino.providers.games.particle.backends.utils",
        )

        # verify expected error was logged
        assert len(error_records) == 1
        assert "Error validating Particle manifest schema version" in error_records[0].message

    def test_raises_with_no_schema_version_in_json(
        self, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Verify missing schema version raises an exception."""
        with pytest.raises(ParticleManifestValidationError):
            validate_manifest_schema_version(
                json.loads('{"cremaVersion": 1}'), _manifest_schema_version
            )

        # get error records
        error_records = filter_caplog(
            caplog.records,
            "merino.providers.games.particle.backends.utils",
        )

        # verify expected errors were logged
        assert len(error_records) == 2
        assert (
            "JSON key error retrieving 'schemaVersion' from manifest JSON."
            == error_records[0].message
        )
        assert "Error validating Particle manifest schema version" in error_records[1].message


class TestValidateManifestAgainstSchema:
    """Tests against validate_manifest_against_schema"""

    def test_does_not_raise_with_valid_json(
        self, valid_manifest_data: Json, manifest_schema_data: Json
    ):
        """Verify no exception raised if manifest JSON is valid."""
        with does_not_raise():
            validate_manifest_against_schema(valid_manifest_data, manifest_schema_data)

    def test_raises_with_invalid_json(
        self,
        invalid_manifest_data: Json,
        manifest_schema_data: Json,
        caplog: LogCaptureFixture,
        filter_caplog: Any,
    ):
        """Verify expected error is raised if manifest JSON does not conform to the schema."""
        with pytest.raises(ParticleManifestValidationError):
            validate_manifest_against_schema(invalid_manifest_data, manifest_schema_data)

        # get error records
        error_records = filter_caplog(
            caplog.records,
            "merino.providers.games.particle.backends.utils",
        )

        # verify expected error was logged
        assert len(error_records) == 1
        assert "Schema validation failed for manifest JSON" in error_records[0].message


class TestRemoteManifestChannelIsUpdated:
    """Tests against remote_manifest_channel_is_updated"""

    test_params = [
        RemoteChannelEnum.RUNTIME,
        RemoteChannelEnum.PUZZLE,
    ]

    @pytest.mark.parametrize("channel", test_params)
    def test_was_updated(self, valid_manifest_data, valid_manifest_data_remote_updated, channel):
        """Test that comparing an old manifest to a new results in an updated signal"""
        assert remote_manifest_channel_is_updated(
            valid_manifest_data_remote_updated, valid_manifest_data, channel
        )

    @pytest.mark.parametrize("channel", test_params)
    def test_was_not_updated(self, valid_manifest_data, channel):
        """Test that comparing the same manifest results in a not updated signal"""
        assert not remote_manifest_channel_is_updated(
            valid_manifest_data, valid_manifest_data, channel
        )


class TestUpdateChannelFiles:
    """Tests against update_channel_files"""

    test_params = [
        RemoteChannelEnum.RUNTIME,
        RemoteChannelEnum.PUZZLE,
    ]

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_update_puzzle_files_should_update_with_gcs_data(
        self, valid_manifest_data, mock_remote_manifest_channel_is_updated, channel
    ):
        """Test that channel files are updated if gcs data exists and versions mismatch"""
        mock_remote_manifest_channel_is_updated.return_value = True

        assert await update_channel_files(valid_manifest_data, valid_manifest_data, channel)

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_update_puzzle_files_should_not_update_with_gcs_data(
        self, valid_manifest_data, mock_remote_manifest_channel_is_updated, channel
    ):
        """Test that channel files are not updated if gcs data exists and versions match"""
        mock_remote_manifest_channel_is_updated.return_value = False

        assert not await update_channel_files(valid_manifest_data, valid_manifest_data, channel)

    @pytest.mark.parametrize("channel", test_params)
    @pytest.mark.asyncio
    async def test_update_puzzle_files_should_update_without_gcs_data(
        self, valid_manifest_data, channel
    ):
        """Test that channel files are updated if gcs data does not exist"""
        assert await update_channel_files(valid_manifest_data, None, channel)


class TestGetRemoteFilesAndShasForChannel:
    """Tests against get_remote_files_and_shas_for_channel."""

    test_params = [
        (
            RemoteChannelEnum.RUNTIME,
            5,
        ),
        (
            RemoteChannelEnum.PUZZLE,
            4,
        ),
    ]

    @pytest.mark.parametrize("channel, file_count", test_params)
    def test_returns_files_and_shas_per_channel(self, valid_manifest_data, channel, file_count):
        """Assert the files found per channel match what's in the manifest JSON."""
        result = get_remote_files_and_shas_for_channel(valid_manifest_data, channel)

        assert len(result) == file_count

    def test_returns_empty_list_for_json_key_error(self, invalid_manifest_data):
        """Assert an empty list is returned if a KeyError happens when looking for files."""
        assert (
            len(
                get_remote_files_and_shas_for_channel(
                    invalid_manifest_data, RemoteChannelEnum.PUZZLE
                )
            )
            == 0
        )


class TestGameFile:
    """Tests against the GameFile class."""

    def test_initialzation(self):
        """Test that initializing a GameFile object sets all expected props."""
        url = "/path/to/a/remote/file.jpg"
        sha = "1234IDeclareASHAWar"
        gf = GameFile(url=url, sha=sha)

        assert gf.remote_url == url
        assert gf.sha_target == sha
        assert gf.remote_path == "/path/to/a/remote"
        assert gf.name == "file.jpg"
        assert not gf.sha_verified


class TestProcessRemoteFilesetForChannel:
    """Tests against the process_remote_fileset_for_channel function."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test success scenario where all files are successfully downloaded and have validated SHAs."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        # match the fake shas above
        mock_compute_sha.side_effect = ["1234abcd", "5678abcd"]

        # ensure the function returns true
        assert await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        # retrieving channel files should happen once
        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # these should be called once for each game file
        assert mock_download_remote_file.call_count == len(mock_game_files)
        assert mock_compute_sha.call_count == len(mock_game_files)

        # all game files should be marked as verified
        assert all(f.sha_verified for f in mock_game_files)

    @pytest.mark.asyncio
    async def test_no_files_in_manifest(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Verify behavior when there are no files found in the manifest for the given channel. (Very edge case.)"""
        mock_get_remote_files_and_shas_for_channel.return_value = []

        # ensure the function returns false
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        # double check retrieving channel files happens once
        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # no processing calls should happen
        assert mock_download_remote_file.call_count == 0
        assert mock_compute_sha.call_count == 0

    @pytest.mark.asyncio
    async def test_first_file_download_fails_with_content_too_short_error(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Verify behavior when the first file download fails with a ContentTooShortError."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        mock_download_remote_file.side_effect = [
            ContentTooShortError("forced error", ("test", "test")),
            mock.DEFAULT,
        ]

        # ensure the function returns false
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        # double check retrieving channel files happens once
        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # only the first call to download_remote_file should happen, as it is
        # forced to raise above
        assert mock_download_remote_file.call_count == 1

        # we should never get to sha validation, as processing should stop when
        # hitting the download_remote_file exception
        assert mock_compute_sha.call_count == 0

        # no game files should be marked as verified
        assert not any(f.sha_verified for f in mock_game_files)

    @pytest.mark.asyncio
    async def test_first_file_download_fails_with_generic_exception(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test behavior when the first file download fails with a generic Error. (Same scenario as test above - just different exception.)"""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        mock_download_remote_file.side_effect = [Exception("forced error"), mock.DEFAULT]

        # ensure the function returns false
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        # double check retrieving channel files happens once
        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # only the first call to download_remote_file should happen, as it is
        # forced to raise above
        assert mock_download_remote_file.call_count == 1

        # we should never get to sha validation, as processing should stop when
        # hitting the download_remote_file exception
        assert mock_compute_sha.call_count == 0

        # no game files should be marked as verified
        assert not any(f.sha_verified for f in mock_game_files)

    @pytest.mark.asyncio
    async def test_second_file_download_fails_with_content_too_short_error(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test behavior when second file download fails with a ContentTooShortError."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        mock_download_remote_file.side_effect = [
            mock.DEFAULT,
            ContentTooShortError("forced error", ("test", "test")),
        ]

        # match the fake shas above
        mock_compute_sha.side_effect = ["1234abcd", "5678abcd"]

        # should be falsy as not all files were processed successfully
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # the first call to download_remote_file should succeed, the second
        # should fail - but two should be made
        assert mock_download_remote_file.call_count == 2

        # sha validation should only happen for the first file, as processing
        # should stop after the second call to download_remote_file fails
        assert mock_compute_sha.call_count == 1

        # only the first file should be marked as verified
        assert mock_game_files[0].sha_verified
        assert not mock_game_files[1].sha_verified

    @pytest.mark.asyncio
    async def test_first_sha_validation_fails(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test behavior when SHA validation fails for the first file."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        # force a mismatch when validating the first SHA
        mock_compute_sha.side_effect = ["SHAmismatch", "5678abcd"]

        # should be falsy as not all files were processed successfully
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # the first call to download_remote_file should succeed, the second
        # shouldn't happen due to processing stopping when the first SHA
        # validation fails
        assert mock_download_remote_file.call_count == 1

        # sha validation should only happen for the first file, as processing
        # should stop after the first SHA validation fails
        assert mock_compute_sha.call_count == 1

        # no game files should be marked as verified
        assert not any(f.sha_verified for f in mock_game_files)

    @pytest.mark.asyncio
    async def test_second_sha_validation_fails(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test behavior when SHA validation fails for the second file."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        # force a mismatch when validating the second SHA
        mock_compute_sha.side_effect = ["1234abcd", "SHAmismatch"]

        # should be falsy as not all files were processed successfully
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # both files should be downloaded
        assert mock_download_remote_file.call_count == 2

        # sha validation should happen for both files
        assert mock_compute_sha.call_count == 2

        # only the first file should be marked as verified
        assert mock_game_files[0].sha_verified
        assert not mock_game_files[1].sha_verified

    @pytest.mark.asyncio
    async def test_first_sha_validation_raises(
        self,
        mock_get_remote_files_and_shas_for_channel,
        mock_download_remote_file,
        mock_compute_sha,
    ):
        """Test behavior when SHA validation raises for the first file."""
        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha="1234abcd"),
            GameFile(url="/path/to/style.css", sha="5678abcd"),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        # force an exception when validating the first sha
        mock_compute_sha.side_effect = [Exception("forced error"), "5678abcd"]

        # should be falsy as not all files were processed successfully
        assert not await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        mock_get_remote_files_and_shas_for_channel.assert_called_once()

        # the first call to download_remote_file should succeed, the second
        # shouldn't happen due to processing stopping when the first SHA
        # validation fails
        assert mock_download_remote_file.call_count == 1

        # sha validation should only happen for the first file, as processing
        # should stop after the first SHA validation fails
        assert mock_compute_sha.call_count == 1

        # no game files should be marked as verified
        assert not any(f.sha_verified for f in mock_game_files)

    @pytest.mark.asyncio
    @patch("requests.get")
    async def test_file_download_to_tempdir_and_real_sha_check(
        self,
        mock_get,
        mock_particle_game_file,
        mock_get_remote_files_and_shas_for_channel,
    ):
        """Test full functionality with only file download contents mocked."""
        # actual binary file data from a local test image file
        mock_get.return_value.content = mock_particle_game_file

        mock_game_files = [
            GameFile(url="/path/to/file.jpg", sha=MOCK_PARTICLE_GAME_FILE_SHA),
        ]

        mock_get_remote_files_and_shas_for_channel.return_value = mock_game_files

        # should be true as download and sha check are successful
        assert await process_remote_fileset_for_channel(
            manifest_remote="{}",
            channel=RemoteChannelEnum.PUZZLE,
            particle_url_root="https://test",
        )

        # explicitly verify the sha computed in the call above matches the
        # expected manually computed sha
        assert mock_game_files[0].sha_computed == MOCK_PARTICLE_GAME_FILE_SHA

        # file should be marked as verified
        assert all(f.sha_verified for f in mock_game_files)
