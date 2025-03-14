# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the Manifest provider unit test directory."""

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from google.auth.credentials import AnonymousCredentials

from merino.configs import settings
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.manifest import ManifestBackend
from merino.providers.manifest.provider import Provider


@pytest.fixture(autouse=True, name="cleanup")
def cleanup_tasks_fixture():
    """Return a method that cleans up existing cron tasks after initialization"""

    async def cleanup_tasks(manifest_provider: Provider):
        """Cleanup cron tasks after initialization"""
        assert manifest_provider.cron_task is not None
        assert not manifest_provider.cron_task.done()

        # Clean up the task
        manifest_provider.cron_task.cancel()
        try:
            await manifest_provider.cron_task
        except asyncio.CancelledError:
            pass

    return cleanup_tasks


@pytest.fixture(name="manifest_remote_filemanager_parameters")
def fixture_manifest_remote_filemanager_parameters() -> dict[str, Any]:
    """Define ManifestRemoteFilemanager parameters for test."""
    return {
        "gcs_project_path": "test_gcp_uploader_project",
        "gcs_bucket_path": "test_gcp_uploader_bucket",
        "blob_name": "test_blob_name",
    }


@pytest.fixture(name="manifest_remote_filemanager")
def fixture_manifest_remote_filemanager(
    manifest_remote_filemanager_parameters: dict[str, Any], gcs_client_mock
) -> ManifestRemoteFilemanager:
    """Create a ManifestRemoteFilemanager object for test."""
    with (
        patch("google.cloud.storage.Client") as mock_client,
        patch("google.auth.default") as mock_auth_default,
    ):
        creds = AnonymousCredentials()  # type: ignore
        mock_auth_default.return_value = (creds, "test-project")
        mock_client.return_value = gcs_client_mock
        return ManifestRemoteFilemanager(**manifest_remote_filemanager_parameters)


@pytest.fixture(name="backend")
def fixture_backend() -> ManifestBackend:
    """Create a Manifest backend object for test."""
    backend = ManifestBackend()
    return backend


@pytest.fixture(name="manifest_parameters")
def fixture_manifest_parameters() -> dict[str, Any]:
    """Define Manifest provider parameters for test."""
    return {
        "resync_interval_sec": settings.manifest.resync_interval_sec,
        "cron_interval_sec": settings.manifest.cron_interval_sec,
    }


@pytest.fixture(name="manifest_provider")
def fixture_top_picks(backend: ManifestBackend, manifest_parameters: dict[str, Any]) -> Provider:
    """Create Manifest Provider for test."""
    return Provider(backend=backend, **manifest_parameters)
