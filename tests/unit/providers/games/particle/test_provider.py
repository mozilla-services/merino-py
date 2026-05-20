# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Particle games provider."""

import asyncio
import json
import logging
import pytest

from logging import LogRecord
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from tests.types import FilterCaplogFixture
from unittest.mock import AsyncMock, patch

from merino.providers.games.particle.backends.filemanager import ParticleFileManagerError
from merino.providers.games.particle.backends.protocol import (
    Particle,
    ParticleBackend,
)
from merino.providers.games.particle.provider import Provider


test_game_url = "https://test.test"


@pytest.fixture()
def valid_manifest_data():
    """Load mock response data from the Particle manifest endpoint."""
    with open("tests/data/games/particle/runtime-manifest.v1.json") as f:
        return f.read()


@pytest.fixture(name="manifest_validation_schema")
def manifest_validation_schema():
    """Load schema to validate manifest."""
    with open("tests/data/games/particle/manifest-validation-schema.json") as f:
        return json.load(f)


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture):
    """Return a mock ParticleBackend."""
    return mocker.AsyncMock(spec=ParticleBackend)


@pytest.fixture(name="provider")
def fixture_provider(
    statsd_mock, backend_mock: ParticleBackend, manifest_validation_schema
) -> Provider:
    """Return a Provider instance for testing."""
    return Provider(
        backend=backend_mock,
        cron_interval_sec=60,
        manifest_schema=manifest_validation_schema,
        manifest_schema_version=1,
        metrics_client=statsd_mock,
        name="particle",
        resync_interval_sec=120,
        enabled=False,
    )


@pytest.fixture(name="test_particle")
def fixture_test_particle() -> Particle:
    """Return a test Particle instance."""
    return Particle(url=test_game_url)


@pytest.fixture
def mock_validate_schema():
    """Return a mocked validate_manifest_against_schema function"""
    with patch(
        "merino.providers.games.particle.provider.validate_manifest_against_schema"
    ) as mock_validate_schema:
        yield mock_validate_schema


@pytest.fixture
def mock_validate_schema_version():
    """Return a mocked validate_manifest_schema_version function"""
    with patch(
        "merino.providers.games.particle.provider.validate_manifest_schema_version"
    ) as mock_validate_schema_version:
        yield mock_validate_schema_version


@pytest.fixture
def mock_fetch_from_gcs(provider):
    """Return a mocked fetch_manifest_json_from_gcs async function"""
    with patch.object(
        provider.backend, "fetch_manifest_json_from_gcs", new=AsyncMock()
    ) as mock_fetch_from_gcs:
        yield mock_fetch_from_gcs


@pytest.fixture
def mock_update_puzzle():
    """Return a mocked update_files_puzzle async function"""
    with patch(
        "merino.providers.games.particle.provider.update_files_puzzle", new=AsyncMock()
    ) as mock_update_puzzle:
        yield mock_update_puzzle


@pytest.fixture
def mock_update_runtime():
    """Return a mocked update_files_runtime async function"""
    with patch(
        "merino.providers.games.particle.provider.update_files_runtime", new=AsyncMock()
    ) as mock_update_runtime:
        yield mock_update_runtime


def test_provider_name(provider: Provider) -> None:
    """Test that the provider name is set correctly."""
    assert provider.name == "particle"


def test_provider_enabled_by_default(provider: Provider) -> None:
    """Test that enabled_by_default is set correctly."""
    assert provider._enabled is False


@pytest.mark.asyncio
async def test_initialize(provider: Provider) -> None:
    """Test that initialize completes without error."""
    await provider.initialize()


@pytest.mark.asyncio
async def test_get_game_url_returns_none_when_backend_returns_none(
    provider: Provider, backend_mock
) -> None:
    """Test that get_game_url returns an empty Particle when backend returns None."""
    backend_mock.get_game_url.return_value = None

    particle = await provider.get_game_url()

    assert particle is None


@pytest.mark.asyncio
async def test_get_game_url_returns_correct_particle(
    provider: Provider, backend_mock, test_particle
) -> None:
    """Test that get_game_url returns a correct Particle instance."""
    backend_mock.get_game_url.return_value = test_particle

    particle = await provider.get_game_url()

    assert particle is not None
    assert particle.url == test_game_url


@pytest.mark.asyncio
async def test_initialize_runs_cron_when_provider_enabled(provider):
    """Initialize should call _fetch_game_data and create cron job when provider is enabled."""
    with (
        patch.object(provider, "_enabled", True),
        patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create_task,
        patch("merino.providers.games.particle.provider.cron.Job") as mock_cron_job,
    ):
        mock_job_instance = AsyncMock(name="mock_cron_job")
        mock_cron_job.return_value = mock_job_instance

        await provider.initialize()

        mock_cron_job.assert_called_once_with(
            name="update_particle_game_data",
            interval=provider.cron_interval_sec,
            condition=provider._should_fetch_data,
            task=provider._fetch_game_data,
        )

        mock_create_task.assert_called_once()
        args, _ = mock_create_task.call_args
        called_arg = args[0]
        assert asyncio.iscoroutine(called_arg)
        assert hasattr(provider, "cron_task")


def test_should_fetch_data_returns_true_when_interval_satsified(provider):
    """_should_fetch_data should return True if the time interval condition is satisfied"""
    with (
        patch("merino.providers.games.particle.provider.time.time", side_effect=[100]),
        patch.object(provider, "resync_interval_sec", 50),
        patch.object(provider, "last_successful_update_at", 50),
    ):
        assert provider._should_fetch_data() is True


def test_should_fetch_data_returns_false_when_interval_not_satsified(provider):
    """_should_fetch_data should return False if the time interval condition is not satisfied"""
    with (
        patch("merino.providers.games.particle.provider.time.time", side_effect=[100]),
        patch.object(provider, "resync_interval_sec", 60),
        patch.object(provider, "last_successful_update_at", 50),
    ):
        assert provider._should_fetch_data() is False


@pytest.mark.asyncio
async def test_fetch_game_data_happy_path(provider, valid_manifest_data):
    """Test that _fetch_game_data retrieves remote json and updates as expected"""
    with (
        patch.object(
            provider.backend, "fetch_manifest_json_from_remote", new=AsyncMock()
        ) as mock_fetch_manifest,
        patch.object(provider, "process_remote_particle_data") as mock_process_data,
        patch("merino.providers.games.particle.provider.time.time", side_effect=[100]),
    ):
        mock_fetch_manifest.return_value = valid_manifest_data
        mock_process_data.return_value = True

        await provider._fetch_game_data()

        mock_fetch_manifest.assert_awaited_once()
        mock_process_data.assert_called_once()
        assert provider.last_successful_update_at == 100


@pytest.mark.asyncio
async def test_fetch_game_data_processing_remote_data_fails(provider, valid_manifest_data):
    """Test that _fetch_game_data retrieves remote json but processing the json fails"""
    with (
        patch.object(
            provider.backend, "fetch_manifest_json_from_remote", new=AsyncMock()
        ) as mock_fetch_manifest,
        patch.object(provider, "process_remote_particle_data") as mock_process_data,
        patch.object(provider, "last_successful_update_at", 0.0),
        patch("merino.providers.games.particle.provider.time.time", side_effect=[100]),
    ):
        mock_fetch_manifest.return_value = valid_manifest_data
        mock_process_data.return_value = False

        await provider._fetch_game_data()

        mock_fetch_manifest.assert_awaited_once()
        mock_process_data.assert_called_once()
        assert provider.last_successful_update_at == 0.0


@pytest.mark.asyncio
async def test_fetch_game_data_remote_fetch_fails(
    provider,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
):
    """Test that _fetch_game_data logs as expected if the remote fetch fails"""
    with (
        patch.object(
            provider.backend, "fetch_manifest_json_from_remote", new=AsyncMock()
        ) as mock_fetch_manifest,
        patch.object(provider, "process_remote_particle_data") as mock_process_data,
        patch.object(provider, "last_successful_update_at", 0.0),
        patch("merino.providers.games.particle.provider.time.time", side_effect=[100]),
    ):
        caplog.set_level(logging.INFO)

        mock_fetch_manifest.side_effect = Exception("kaboom!")

        await provider._fetch_game_data()

        mock_fetch_manifest.assert_awaited_once()
        mock_process_data.assert_not_awaited()

        # ensure the last_successful_update_at value was not updated
        assert provider.last_successful_update_at == 0.0

        records: list[LogRecord] = filter_caplog(
            caplog.records, "merino.providers.games.particle.provider"
        )

        # verify logging
        assert len(records) == 2
        assert records[0].message.startswith(
            "Failed to fetch Particle game data from remote endpoint"
        )
        assert records[1].message.startswith(
            "Particle game data fetch returned None - will retry on next cron tick"
        )


@pytest.mark.asyncio
async def test_process_remote_particle_data_puzzle_and_runtime_updated(
    provider,
    valid_manifest_data,
    mock_validate_schema,
    mock_validate_schema_version,
    mock_fetch_from_gcs,
    mock_update_puzzle,
    mock_update_runtime,
):
    """Assert process_remote_particle_data returns True and all expected functions are called when both puzzle and runtime files require updating"""
    mock_update_puzzle.return_value = True
    mock_update_runtime.return_value = True

    assert await provider.process_remote_particle_data(valid_manifest_data)

    mock_validate_schema.assert_called_once()
    mock_validate_schema_version.assert_called_once()
    mock_fetch_from_gcs.assert_awaited_once()
    mock_update_puzzle.assert_awaited_once()
    mock_update_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_remote_particle_data_puzzle_updated(
    provider,
    valid_manifest_data,
    mock_validate_schema,
    mock_validate_schema_version,
    mock_fetch_from_gcs,
    mock_update_puzzle,
    mock_update_runtime,
):
    """Assert process_remote_particle_data returns True and all expected functions are called when only puzzle files require updating"""
    mock_update_puzzle.return_value = True
    mock_update_runtime.return_value = False

    assert await provider.process_remote_particle_data(valid_manifest_data)

    mock_validate_schema.assert_called_once()
    mock_validate_schema_version.assert_called_once()
    mock_fetch_from_gcs.assert_awaited_once()
    mock_update_puzzle.assert_awaited_once()
    mock_update_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_remote_particle_data_runtime_updated(
    provider,
    valid_manifest_data,
    mock_validate_schema,
    mock_validate_schema_version,
    mock_fetch_from_gcs,
    mock_update_puzzle,
    mock_update_runtime,
):
    """Assert process_remote_particle_data returns True and all expected functions are called when only runtime files require updating"""
    mock_update_puzzle.return_value = False
    mock_update_runtime.return_value = True

    assert await provider.process_remote_particle_data(valid_manifest_data)

    mock_validate_schema.assert_called_once()
    mock_validate_schema_version.assert_called_once()
    mock_fetch_from_gcs.assert_awaited_once()
    mock_update_puzzle.assert_awaited_once()
    mock_update_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_remote_particle_data_no_files_updated(
    provider,
    valid_manifest_data,
    mock_validate_schema,
    mock_validate_schema_version,
    mock_fetch_from_gcs,
    mock_update_puzzle,
    mock_update_runtime,
):
    """Assert process_remote_particle_data returns False and all expected functions are called when no files require updating"""
    mock_update_puzzle.return_value = False
    mock_update_runtime.return_value = False

    assert not await provider.process_remote_particle_data(valid_manifest_data)

    mock_validate_schema.assert_called_once()
    mock_validate_schema_version.assert_called_once()
    mock_fetch_from_gcs.assert_awaited_once()
    mock_update_puzzle.assert_awaited_once()
    mock_update_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_remote_particle_data_gcs_fetch_raises(
    provider,
    valid_manifest_data,
    mock_validate_schema,
    mock_validate_schema_version,
    mock_fetch_from_gcs,
    mock_update_puzzle,
    mock_update_runtime,
):
    """Assert process_remote_particle_data returns False and all expected functions are called when no files require updating"""
    mock_fetch_from_gcs.side_effect = ParticleFileManagerError("GCS call failed")

    assert not await provider.process_remote_particle_data(valid_manifest_data)

    mock_validate_schema.assert_called_once()
    mock_validate_schema_version.assert_called_once()
    mock_fetch_from_gcs.assert_awaited_once()
    mock_update_puzzle.assert_not_awaited()
    mock_update_runtime.assert_not_awaited()
