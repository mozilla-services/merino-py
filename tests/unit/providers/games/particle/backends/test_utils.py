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

from merino.configs import settings
from merino.providers.games.particle.backends.errors import ParticleManifestValidationError
from merino.providers.games.particle.backends.utils import (
    GameFile,
    get_remote_files_and_shas_for_channel,
    RemoteChannelEnum,
    remote_manifest_channel_is_updated,
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
        content_type = "image/jpeg"
        gf = GameFile(url=url, sha=sha, content_type=content_type)

        assert gf.remote_url == url
        assert gf.sha_target == sha
        assert gf.remote_path == "/path/to/a/remote"
        assert gf.name == "file.jpg"
        assert gf.content_type == content_type
        assert not gf.sha_verified
