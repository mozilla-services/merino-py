# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for SyncedGcsBlobV2 and typed_gcs_json_blob_factory.
See also integration tests for coverage of fetch behavior with
fake GCS bucket.
"""

import logging
from datetime import datetime
from unittest.mock import MagicMock

import aiohttp
import orjson
import pytest
from gcloud.aio.storage import Storage
from pydantic import BaseModel
from pytest_mock import MockerFixture

from merino.utils.synced_gcs_blob_v2 import (
    SyncedGcsBlobV2,
    typed_gcs_json_blob_factory,
)

BUCKET_NAME = "test-bucket"
BLOB_NAME = "test/data.json"
MAX_SIZE = 1024
BLOB_UPDATED = "2024-01-15T12:00:00+00:00"
DEFAULT_TAGS = {"bucket": BUCKET_NAME, "blob": BLOB_NAME}


class FakeModel(BaseModel):
    """Minimal Pydantic model for tests."""

    value: int


@pytest.fixture
def mock_storage(mocker: MockerFixture) -> MagicMock:
    """Return a mock async Storage client."""
    return mocker.MagicMock(spec=Storage)


@pytest.fixture
def mock_blob(mocker: MockerFixture) -> MagicMock:
    """Return a mock async GCS Blob with sensible defaults."""
    blob = mocker.AsyncMock()
    blob.size = "100"
    blob.updated = BLOB_UPDATED
    blob.download = mocker.AsyncMock(return_value=orjson.dumps({"value": 1}))
    return blob


@pytest.fixture
def mock_bucket(mocker: MockerFixture, mock_blob: MagicMock) -> MagicMock:
    """Return a mock async GCS Bucket whose get_blob returns mock_blob."""
    bucket = mocker.AsyncMock()
    bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)
    return bucket


@pytest.fixture
def synced(
    mock_storage: MagicMock, mock_bucket: MagicMock, statsd_mock: MagicMock
) -> SyncedGcsBlobV2:
    """Return a SyncedGcsBlobV2 with its internal bucket replaced by the mock."""
    instance: SyncedGcsBlobV2[FakeModel] = SyncedGcsBlobV2(
        storage_client=mock_storage,
        metrics_client=statsd_mock,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=60,
        cron_job_name="test_job",
        fetch_callback=lambda raw: FakeModel.model_validate(orjson.loads(raw)),
    )
    instance._bucket = mock_bucket
    return instance


def test_accessing_data_while_none_emits_not_ready_metric(
    synced: SyncedGcsBlobV2, statsd_mock: MagicMock
) -> None:
    """Data returns None and emits data.not_ready metric before any fetch.
    Note: in here and other tests, passing in the same mock that was used
    to initialize the `synced` fixture to avoid type complaints about
    StatsdClient, rather than accessing directly through synced fixture.
    """
    assert synced.data is None
    statsd_mock.increment.assert_called_once_with("gcs.sync.data.not_ready", tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_update_task_fetches_and_stores_data(
    synced: SyncedGcsBlobV2, mock_blob: MagicMock, statsd_mock: MagicMock
) -> None:
    """A successful fetch populates data, increments update_count, and emits valid=1."""
    mock_blob.download.return_value = orjson.dumps({"value": 42})

    await synced._update_task()

    assert synced.data == FakeModel(value=42)
    assert synced.update_count == 1
    assert synced.last_updated == datetime.fromisoformat(BLOB_UPDATED)
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=1, tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_update_task_emits_size_metric(
    synced: SyncedGcsBlobV2, mock_blob: MagicMock, statsd_mock: MagicMock
) -> None:
    """A successful fetch emits the blob size as a gauge."""
    mock_blob.size = "512"

    await synced._update_task()

    statsd_mock.gauge.assert_any_call("gcs.sync.size", value=512, tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_update_task_emits_staleness_metric_after_fetch(
    synced: SyncedGcsBlobV2, statsd_mock: MagicMock
) -> None:
    """After a successful fetch, last_updated staleness gauge is emitted."""
    await synced._update_task()

    call_keys = [call[0][0] for call in statsd_mock.gauge.call_args_list]
    assert "gcs.sync.last_updated" in call_keys


@pytest.mark.asyncio
async def test_update_task_logs_error_when_blob_too_large(
    synced: SyncedGcsBlobV2,
    mock_blob: MagicMock,
    statsd_mock: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A blob exceeding max_size logs an error, emits valid=0, and does not download."""
    mock_blob.size = str(MAX_SIZE + 1)

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert f"size {MAX_SIZE + 1} exceeds {MAX_SIZE}" in caplog.text
    mock_blob.download.assert_not_called()
    assert synced.update_count == 0
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=0, tags=DEFAULT_TAGS)


@pytest.fixture
def http_error(mocker: MockerFixture):
    """Return an aiohttp.ClientResponseError with a given status."""

    def _http_error(status: int) -> aiohttp.ClientResponseError:
        return aiohttp.ClientResponseError(request_info=mocker.Mock(), history=(), status=status)

    return _http_error


@pytest.mark.asyncio
async def test_update_task_logs_error_on_404(
    synced: SyncedGcsBlobV2,
    mock_bucket: MagicMock,
    statsd_mock: MagicMock,
    http_error,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 from get_blob logs a not-found error and increments fetch.response with status=404."""
    mock_bucket.get_blob.side_effect = http_error(404)

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert f"Blob '{BLOB_NAME}' not found." in caplog.text
    assert synced.update_count == 0
    statsd_mock.increment.assert_any_call(
        "gcs.sync.fetch.response", tags=DEFAULT_TAGS | {"status": 404}
    )


@pytest.mark.asyncio
async def test_update_task_logs_error_on_other_http_errors(
    synced: SyncedGcsBlobV2,
    mock_bucket: MagicMock,
    statsd_mock: MagicMock,
    http_error,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-404 HTTP error from get_blob logs a generic error and increments fetch.response with that status."""
    mock_bucket.get_blob.side_effect = http_error(503)

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert f"Error fetching blob metadata for '{BLOB_NAME}'" in caplog.text
    assert synced.update_count == 0
    statsd_mock.increment.assert_any_call(
        "gcs.sync.fetch.response", tags=DEFAULT_TAGS | {"status": 503}
    )


@pytest.mark.asyncio
async def test_update_task_increments_fetch_response_200_on_success(
    synced: SyncedGcsBlobV2, statsd_mock: MagicMock
) -> None:
    """A successful get_blob increments fetch.response with status=200."""
    await synced._update_task()

    statsd_mock.increment.assert_any_call(
        "gcs.sync.fetch.response", tags=DEFAULT_TAGS | {"status": 200}
    )


@pytest.mark.asyncio
async def test_update_task_handles_json_decode_error(
    synced: SyncedGcsBlobV2,
    mock_blob: MagicMock,
    statsd_mock: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed JSON payload logs an error, emits valid=0, and does not advance state."""
    mock_blob.download.return_value = b"not valid json {"

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert "Failed to decode blob JSON" in caplog.text
    assert synced.data is None
    assert synced.update_count == 0
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=0, tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_update_task_handles_validation_error(
    synced: SyncedGcsBlobV2,
    mock_blob: MagicMock,
    statsd_mock: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A payload that fails Pydantic validation logs an error and emits valid=0."""
    mock_blob.download.return_value = orjson.dumps({"value": "not-an-int"})

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert "Invalid blob content" in caplog.text
    assert synced.update_count == 0
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=0, tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_update_task_handles_generic_exception(
    synced: SyncedGcsBlobV2,
    mock_blob: MagicMock,
    statsd_mock: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected exception from fetch_callback logs an error and emits valid=0."""
    mock_blob.download.return_value = orjson.dumps({"value": 1})

    def exploding_callback(raw: bytes) -> FakeModel:
        raise RuntimeError("unexpected failure")

    synced.fetch_callback = exploding_callback

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert "Blob fetch failure" in caplog.text
    assert synced.update_count == 0
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=0, tags=DEFAULT_TAGS)


## Tests for typed_gcs_json_blob_factory


@pytest.mark.asyncio
async def test_factory_parses_model_and_emits_valid_metric(
    mock_storage: MagicMock, mock_bucket: MagicMock, statsd_mock: MagicMock, mock_blob: MagicMock
) -> None:
    """typed_gcs_json_blob_factory produces a SyncedGcsBlobV2 that parses the model correctly."""
    mock_blob.download.return_value = orjson.dumps({"value": 7})

    synced = typed_gcs_json_blob_factory(
        model=FakeModel,
        storage_client=mock_storage,
        metrics_client=statsd_mock,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=60,
        cron_job_name="factory_test",
    )
    synced._bucket = mock_bucket

    await synced._update_task()

    assert synced.data == FakeModel(value=7)
    statsd_mock.gauge.assert_any_call("gcs.sync.valid", value=1, tags=DEFAULT_TAGS)


@pytest.mark.asyncio
async def test_factory_raises_on_invalid_json(
    mock_storage: MagicMock,
    mock_bucket: MagicMock,
    statsd_mock: MagicMock,
    mock_blob: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """typed_gcs_json_blob_factory: invalid JSON is caught by _update_task and logged."""
    mock_blob.download.return_value = b"{"

    synced = typed_gcs_json_blob_factory(
        model=FakeModel,
        storage_client=mock_storage,
        metrics_client=statsd_mock,
        bucket_name=BUCKET_NAME,
        blob_name=BLOB_NAME,
        max_size=MAX_SIZE,
        cron_interval_seconds=60,
        cron_job_name="factory_test_invalid",
    )
    synced._bucket = mock_bucket

    with caplog.at_level(logging.ERROR):
        await synced._update_task()

    assert synced.data is None
    assert "Failed to decode blob JSON" in caplog.text
