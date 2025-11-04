# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the manifest provider module."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from merino.providers.manifest.backends.protocol import (
    GetManifestResultCode,
    ManifestBackendError,
    ManifestData,
)
from merino.providers.manifest.provider import Provider
from merino.providers.manifest.backends.manifest import ManifestBackend


@pytest.mark.asyncio
async def test_initialize(
    manifest_provider: Provider,
    backend: ManifestBackend,
    manifest_data: ManifestData,
    cleanup,
) -> None:
    """Test initialization of manifest provider"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        result_code, _ = await backend.fetch()

        assert result_code is GetManifestResultCode.SUCCESS
        assert manifest_provider.manifest_data == manifest_data
        assert manifest_provider.last_fetch_at > 0


@pytest.mark.asyncio
async def test_get_manifest_data(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test get_manifest_data method returns manifest data"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        result = manifest_provider.get_manifest_data()
        assert result is not None
        assert result == manifest_provider.manifest_data
        assert manifest_provider.manifest_data == manifest_data


@pytest.mark.asyncio
async def test_should_fetch_true(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test should_fetch method returns true based on the resync interval"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        # difference between last fetch and current time is 100000 (greater than 86400)
        with patch(
            "merino.providers.manifest.provider.time.time",
            side_effect=[100000, 200000, 300000],
        ):
            await manifest_provider.initialize()
            await cleanup(manifest_provider)

            should_fetch = manifest_provider._should_fetch()

            assert should_fetch is True


@pytest.mark.asyncio
async def test_should_fetch_false(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test should_fetch method returns false based on the resync interval"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        with patch(
            "merino.providers.manifest.provider.time.time",
            side_effect=[100000, 101000, 101500],
        ):
            await manifest_provider.initialize()
            await cleanup(manifest_provider)

            should_fetch = manifest_provider._should_fetch()

            assert should_fetch is False


@pytest.mark.asyncio
async def test_fetch_data_success(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test fetch_data method sets manifest data on SUCCESS"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data == manifest_data


@pytest.mark.asyncio
async def test_fetch_data_fail(manifest_provider: Provider, cleanup) -> None:
    """Test fetch_data method does not set manifest data when a failure occurs"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.FAIL, None),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        # manifest data remains empty ManifestData instance after initialization
        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data.domains == []


@pytest.mark.asyncio
async def test_fetch_data_error(manifest_provider: Provider, cleanup) -> None:
    """Test fetch_data method does not set manifest data when an error occurs"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        side_effect=ManifestBackendError,
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        # manifest data remains empty ManifestData instance after initialization
        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data.domains == []


@pytest.mark.asyncio
async def test_initialize_runs_cron_and_fetch_when_gcs_enabled(manifest_provider):
    """Initialize should call _fetch_data and create cron job when GCS is enabled."""
    with (
        patch("merino.providers.manifest.provider.settings") as mock_settings,
        patch.object(manifest_provider, "_fetch_data", new=AsyncMock()) as mock_fetch_data,
        patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create_task,
        patch("merino.providers.manifest.provider.cron.Job") as mock_job,
    ):
        mock_settings.image_gcs.gcs_enabled = True

        mock_job_instance = AsyncMock(name="mock_cron_job")
        mock_job.return_value = mock_job_instance

        await manifest_provider.initialize()

        mock_fetch_data.assert_awaited_once()

        mock_job.assert_called_once_with(
            name="resync_manifest",
            interval=manifest_provider.cron_interval_sec,
            condition=manifest_provider._should_fetch,
            task=manifest_provider._fetch_data,
        )

        mock_create_task.assert_called_once()
        args, _ = mock_create_task.call_args
        called_arg = args[0]
        assert asyncio.iscoroutine(called_arg)
        assert hasattr(manifest_provider, "cron_task")


@pytest.mark.asyncio
async def test_initialize_does_not_run_when_gcs_disabled(manifest_provider):
    """Initialize should skip _fetch_data and cron job creation when GCS is disabled."""
    with (
        patch("merino.providers.manifest.provider.settings") as mock_settings,
        patch.object(manifest_provider, "_fetch_data", new=AsyncMock()) as mock_fetch_data,
        patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create_task,
        patch("merino.providers.manifest.provider.cron.Job") as mock_job,
    ):
        mock_settings.image_gcs.gcs_enabled = False

        await manifest_provider.initialize()

        mock_fetch_data.assert_not_awaited()

        mock_job.assert_not_called()
        mock_create_task.assert_not_called()
        assert not hasattr(manifest_provider, "cron_task")
