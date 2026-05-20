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
from unittest.mock import patch

from merino.configs import settings
from merino.providers.games.particle.backends.utils import (
    ParticleManifestValidationError,
    remote_manifest_puzzle_is_updated,
    remote_manifest_runtime_is_updated,
    update_files_puzzle,
    update_files_runtime,
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
def mock_remote_manifest_puzzle_is_updated():
    """Return mock remote_manifest_puzzle_is_updated function"""
    with patch(
        "merino.providers.games.particle.backends.utils.remote_manifest_puzzle_is_updated"
    ) as mock_remote_manifest_puzzle_is_updated:
        yield mock_remote_manifest_puzzle_is_updated


@pytest.fixture
def mock_remote_manifest_runtime_is_updated():
    """Return mock remote_manifest_runtime_is_updated function"""
    with patch(
        "merino.providers.games.particle.backends.utils.remote_manifest_runtime_is_updated"
    ) as mock_remote_manifest_runtime_is_updated:
        yield mock_remote_manifest_runtime_is_updated


# END FIXTURES


# BEGIN validate_manifest_schema_version TESTS
def test_validate_manifest_schema_version_does_not_raise_with_valid_json(valid_manifest_data):
    """Verify valid JSON results in no exception raised."""
    with does_not_raise():
        validate_manifest_schema_version(valid_manifest_data, _manifest_schema_version)


def test_validate_manifest_schema_version_raises_with_invalid_json(
    caplog: LogCaptureFixture, filter_caplog: Any
):
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
            "JSON error retrieving 'schemaVersion' from manifest JSON." == error_records[0].message
        )


def test_validate_manifest_schema_version_raises_with_invalid_schema_version(
    caplog: LogCaptureFixture, filter_caplog: Any
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


def test_validate_manifest_schema_version_raises_with_no_schema_version_in_json(
    caplog: LogCaptureFixture, filter_caplog: Any
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
        "JSON key error retrieving 'schemaVersion' from manifest JSON." == error_records[0].message
    )
    assert "Error validating Particle manifest schema version" in error_records[1].message


# END validate_manifest_schema_version TESTS


# BEGIN validate_manifest_against_schema TESTS
def test_validate_manifest_against_schema_does_not_raise_with_valid_json(
    valid_manifest_data: Json, manifest_schema_data: Json
):
    """Verify no exception raised if manifest JSON is valid."""
    with does_not_raise():
        validate_manifest_against_schema(valid_manifest_data, manifest_schema_data)


def test_validate_manifest_against_schema_raises_with_invalid_json(
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


# END validate_manifest_against_schema TESTS


def test_remote_manifest_runtime_is_updated_was_updated(
    valid_manifest_data, valid_manifest_data_remote_updated
):
    """Test that comparing an old manifest to a new results in an updated signal"""
    assert remote_manifest_runtime_is_updated(
        valid_manifest_data_remote_updated, valid_manifest_data
    )


def test_remote_manifest_runtime_is_updated_was_not_updated(valid_manifest_data):
    """Test that comparing the same manifest results in a not updated signal"""
    assert not remote_manifest_runtime_is_updated(valid_manifest_data, valid_manifest_data)


def test_remote_manifest_puzzle_is_updated_was_updated(
    valid_manifest_data, valid_manifest_data_remote_updated
):
    """Test that comparing an old manifest to a new results in an updated signal"""
    assert remote_manifest_puzzle_is_updated(
        valid_manifest_data_remote_updated, valid_manifest_data
    )


def test_remote_manifest_puzzle_is_updated_was_not_updated(valid_manifest_data):
    """Test that comparing the same manifest results in a not updated signal"""
    assert not remote_manifest_puzzle_is_updated(valid_manifest_data, valid_manifest_data)


# BEGIN update_files_puzzle TESTS
@pytest.mark.asyncio
async def test_update_files_puzzle_should_update_with_gcs_data(
    valid_manifest_data, mock_remote_manifest_puzzle_is_updated
):
    """Test that puzzle files are updated if gcs data exists and versions mismatch"""
    mock_remote_manifest_puzzle_is_updated.return_value = True

    assert await update_files_puzzle(valid_manifest_data, valid_manifest_data)


@pytest.mark.asyncio
async def test_update_files_puzzle_should_not_update_with_gcs_data(
    valid_manifest_data, mock_remote_manifest_puzzle_is_updated
):
    """Test that puzzle files are not updated if gcs data exists and versions match"""
    mock_remote_manifest_puzzle_is_updated.return_value = False

    assert not await update_files_puzzle(valid_manifest_data, valid_manifest_data)


@pytest.mark.asyncio
async def test_update_files_puzzle_should_update_without_gcs_data(valid_manifest_data):
    """Test that puzzle files are updated if gcs data does not exist"""
    assert await update_files_puzzle(valid_manifest_data, None)


# END update_files_puzzle TESTS


# BEGIN update_files_runtime TESTS
@pytest.mark.asyncio
async def test_update_files_runtime_should_update_with_gcs_data(
    valid_manifest_data, mock_remote_manifest_runtime_is_updated
):
    """Test that runtime files are updated if gcs data exists and versions mismatch"""
    mock_remote_manifest_runtime_is_updated.return_value = True

    assert await update_files_runtime(valid_manifest_data, valid_manifest_data)


@pytest.mark.asyncio
async def test_update_files_runtime_should_not_update_with_gcs_data(
    valid_manifest_data, mock_remote_manifest_runtime_is_updated
):
    """Test that runtime files are not updated if gcs data exists and versions match"""
    mock_remote_manifest_runtime_is_updated.return_value = False

    assert not await update_files_runtime(valid_manifest_data, valid_manifest_data)


@pytest.mark.asyncio
async def test_update_files_runtime_should_update_without_gcs_data(valid_manifest_data):
    """Test that runtime files are updated if gcs data does not exist"""
    assert await update_files_runtime(valid_manifest_data, None)


# END update_files_runtime TESTS
