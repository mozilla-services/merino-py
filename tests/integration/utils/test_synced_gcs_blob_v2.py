# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration smoke tests for SyncedGcsBlobV2"""

import asyncio
import logging
import time

import orjson
import pytest
import pytest_asyncio
from gcloud.aio.storage import Storage
from pydantic import BaseModel

from merino.utils.synced_gcs_blob_v2 import (
    LAST_UPDATED_INITIAL_VALUE,
    SyncedGcsBlobV2,
    typed_gcs_json_blob_factory,
)

BUCKET_NAME = "test-synced-gcs-blob-v2"
BLOB_NAME = "test/data.json"
MAX_SIZE = 10 * 1024 * 1024  # 10 MB
CRON_INTERVAL = 0.02  # 20ms


class FakeModel(BaseModel):
    """Minimal Pydantic model used as the blob payload in tests."""

    value: int


@pytest.fixture(scope="module")
def gcs_bucket(gcs_storage_client):
    """Create and tear down an isolated bucket for this test module."""
    bucket = gcs_storage_client.create_bucket(BUCKET_NAME)
    yield bucket
    bucket.delete(force=True)


@pytest_asyncio.fixture
async def async_storage():
    """Return an async gcloud.aio Storage client and clean up after testing.

    Note: STORAGE_EMULATOR_HOST is set by the gcs_storage_container fixture, which causes
    Storage() to skip authentication and route all requests to the local fake-gcs-server.
    """
    client = Storage()
    yield client
    await client.close()


def _upload(gcs_bucket, payload: dict) -> None:
    """Upload a JSON payload to the test blob using the sync client (test setup)."""
    blob = gcs_bucket.blob(BLOB_NAME)
    blob.upload_from_string(orjson.dumps(payload).decode())


async def _wait_for_update(synced: SyncedGcsBlobV2, initial_count: int = 0, timeout=1.0) -> None:
    """Test helper method; poll until update_count advances past initial_count, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if synced.update_count > initial_count:
            return
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_fetches_blob_and_parses_model(gcs_bucket, async_storage, metrics_client):
    """Data uploaded to GCS is fetched, parsed, and accessible via .data."""
    _upload(gcs_bucket, {"value": 42})

    synced = typed_gcs_json_blob_factory(
        model=FakeModel,
        storage_client=async_storage,
        metrics_client=metrics_client,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=CRON_INTERVAL,
        cron_job_name="test_fetches_blob",
    )
    synced.initialize()
    await _wait_for_update(synced)

    assert synced.data == FakeModel(value=42)
    assert synced.update_count == 1


@pytest.mark.asyncio
async def test_data_is_none_before_first_fetch(async_storage, metrics_client):
    """Data is None when accessed before the first successful fetch."""
    synced: SyncedGcsBlobV2[FakeModel] = SyncedGcsBlobV2(
        storage_client=async_storage,
        metrics_client=metrics_client,
        bucket_name=BUCKET_NAME,
        blob_name="nonexistent/blob.json",
        max_size=MAX_SIZE,
        cron_interval_seconds=CRON_INTERVAL,
        cron_job_name="test_data_none",
        fetch_callback=lambda raw: FakeModel.model_validate(orjson.loads(raw)),
    )
    # Do not initialize as that will trigger a cron execution
    assert synced.data is None


@pytest.mark.asyncio
async def test_missing_blob_logs_error(async_storage, metrics_client, caplog):
    """A missing blob logs an error and leaves data as None."""
    synced: SyncedGcsBlobV2[FakeModel] = SyncedGcsBlobV2(
        storage_client=async_storage,
        metrics_client=metrics_client,
        bucket_name=BUCKET_NAME,
        blob_name="does/not/exist.json",
        max_size=MAX_SIZE,
        cron_interval_seconds=CRON_INTERVAL,
        cron_job_name="test_missing_blob",
        fetch_callback=lambda raw: FakeModel.model_validate(orjson.loads(raw)),
    )
    synced.initialize()

    caplog.set_level(logging.ERROR)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if "does/not/exist.json" in caplog.text:
            break
        await asyncio.sleep(0.01)

    assert "does/not/exist.json" in caplog.text
    assert synced.data is None
    assert synced.update_count == 0


@pytest.mark.asyncio
async def test_unchanged_blob_is_not_re_fetched(gcs_bucket, async_storage, metrics_client):
    """Polling a blob that has not changed does not increment update_count,
    but does update `last_updated`.
    """
    _upload(gcs_bucket, {"value": 7})

    synced = typed_gcs_json_blob_factory(
        model=FakeModel,
        storage_client=async_storage,
        metrics_client=metrics_client,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=CRON_INTERVAL,
        cron_job_name="test_unchanged_blob",
    )
    synced.initialize()
    await _wait_for_update(synced)
    assert synced.update_count == 1

    # Let several more cron ticks pass and confirm count stays at 1.
    await asyncio.sleep(CRON_INTERVAL * 5)
    assert synced.update_count == 1
    assert synced.last_updated > LAST_UPDATED_INITIAL_VALUE


@pytest.mark.asyncio
async def test_picks_up_new_version_after_update(gcs_bucket, async_storage, metrics_client):
    """When a blob is re-uploaded with new content, the next poll fetches it."""
    _upload(gcs_bucket, {"value": 1})

    synced = typed_gcs_json_blob_factory(
        model=FakeModel,
        storage_client=async_storage,
        metrics_client=metrics_client,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=CRON_INTERVAL,
        cron_job_name="test_picks_up_new_version",
    )
    synced.initialize()
    await _wait_for_update(synced)
    assert synced.data == FakeModel(value=1)

    _upload(gcs_bucket, {"value": 99})
    await _wait_for_update(synced, initial_count=1)

    assert synced.data == FakeModel(value=99)
    assert synced.update_count == 2
