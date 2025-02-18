# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the Manifest provider unit test directory."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock
import pytest_asyncio

import pytest

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
        "gcs_bucket_path": "test_gcp_uploader_bucket",
        "blob_name": "test_blob_name",
    }


@pytest_asyncio.fixture
async def fixture_filemanager_blob(blob_json):
    """Fixture for a mocked blob."""
    blob = AsyncMock()
    blob.download.return_value = blob_json
    blob.size = 1234
    return blob


@pytest_asyncio.fixture
async def fixture_filemanager_bucket(fixture_filemanager_blob):
    """Fixture for a mocked bucket."""
    bucket = AsyncMock()
    bucket.get_blob.return_value = fixture_filemanager_blob
    return bucket


@pytest_asyncio.fixture
async def fixture_filemanager_storage(fixture_filemanager_bucket):
    """Fixture for a mocked storage client."""
    storage = AsyncMock()
    storage.bucket.return_value = fixture_filemanager_bucket
    return storage


@pytest_asyncio.fixture
async def fixture_filemanager(fixture_filemanager_storage, fixture_filemanager_bucket):
    """Fixture for an instantiated filemanager with mocked GCS client and bucket."""
    file_manager = ManifestRemoteFilemanager("test-bucket", "test-blob")
    file_manager.gcs_client = fixture_filemanager_storage
    file_manager.bucket = fixture_filemanager_bucket
    return file_manager


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
