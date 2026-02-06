"""Tests loading engagement data from Google Cloud Storage."""

import asyncio
import base64
import logging
import time
from typing import Callable

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Bucket

from merino.configs import settings
from merino.curated_recommendations.ml_backends.gcs_interest_cohort_model import (
    NO_CLICKS_COHORT_ID,
    GcsInterestCohortModel,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

MODEL_BASE64 = "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"


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(settings.interest_cohort_model.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def create_cohort_model(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> GcsInterestCohortModel:
    """Return an initialized GcsInterestCohortModel instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.interest_cohort_model.gcs.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.ml.interest_cohort_model",
        max_size=settings.interest_cohort_model.gcs.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_ml_cohort_model",
        is_bytes=True,
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GcsInterestCohortModel(synced_gcs_blob=synced_gcs_blob)


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.interest_cohort_model.gcs.blob_name)
    blob.upload_from_string(data=data, content_type="application/octet-stream")
    return blob


async def wait(until: Callable[[], bool]):
    """Wait for some time to pass, until the given condition is true."""
    max_wait_time_sec = 2
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if until():
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


async def wait_until_model_is_updated(backend: GcsInterestCohortModel):
    """Wait for some time to pass to update engagement."""
    await wait(until=lambda: backend.update_count > 0)


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        base64.b64decode(MODEL_BASE64),
    )


@pytest.fixture
def old_blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        base64.b64decode(MODEL_BASE64),
    )


@pytest.fixture
def large_blob(gcs_bucket):
    """Create a large blob in the fake GCS server."""
    return create_blob(
        gcs_bucket,
        "a" * (settings.interest_cohort_model.gcs.max_size + 1),
    )


@pytest.fixture(params=["stage", "prod", "dev"])
def setting_environment(request):
    """Fixture to run a test in the staging, production, and development environment."""
    original_env = settings.current_env

    # Set the desired environment.
    settings.configure(FORCE_ENV_FOR_DYNACONF=request.param)
    yield request.param  # Yield to run the test

    # Reset to the original environment after the test
    settings.configure(FORCE_ENV_FOR_DYNACONF=original_env)


@pytest.mark.asyncio
async def test_cohort_model_works(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend parses model."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)
    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model", interests="0100" * (model_provider._num_bits // 4)
    )
    assert result is not None
    int_result: int | None = None
    try:
        int_result = int(result)
    except ValueError:
        int_result = None
    assert int_result is not None
    assert int_result >= 0
    assert int_result < 20

    # Special case with no interests
    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model", interests="1000" * (model_provider._num_bits // 4)
    )
    assert result == NO_CLICKS_COHORT_ID


@pytest.mark.asyncio
async def test_normalize_interests_applies_chunk_rewrites(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that _normalize_interests rewrites 4-bit chunks per the normalization rules."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    # Build an interests bitstring out of 4-bit chunks:
    # - include each rewrite case at least once
    # - include a chunk that should pass through unchanged
    chunks_in = [
        "1010",  # -> 0100
        "0101",  # -> 0010
        "1100",  # -> 0100
        "0110",  # -> 0010
        "0011",  # -> 0010
        "1001",  # -> 0010
        "1101",  # -> 0000
        "1011",  # -> 0000
        "0111",  # -> 0000
        "1110",  # -> 0000
        "0001",  # unchanged (control)
    ]
    chunks_out = [
        "0100",
        "0010",
        "0100",
        "0010",
        "0010",
        "0010",
        "0000",
        "0000",
        "0000",
        "0000",
        "0001",
    ]

    interests_in = "".join(chunks_in)
    normalized_out = "".join(chunks_out)

    # first set of items
    test_in = interests_in[: model_provider._num_bits]
    test_out = normalized_out[: model_provider._num_bits]

    result = model_provider._normalize_interests(test_in)
    assert result == test_out

    # second set of items
    test_in = interests_in[: -model_provider._num_bits]
    test_out = normalized_out[: -model_provider._num_bits]

    result = model_provider._normalize_interests(test_in)
    assert result == test_out


@pytest.mark.asyncio
async def test_normalize_interests_raises_on_wrong_length(
    gcs_storage_client, gcs_bucket, metrics_client, blob
):
    """Test that _normalize_interests rejects strings of incorrect length."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    assert model_provider._num_bits == 32
    assert model_provider._normalize_interests("0" * (model_provider._num_bits - 1)) is None


@pytest.mark.asyncio
async def test_empty_interests(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that _normalize_interests rejects strings of incorrect length."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    assert model_provider._num_bits == 32
    assert model_provider._is_empty_cohort_for_no_clicks("1000" * 8) is True
    assert model_provider._is_empty_cohort_for_no_clicks("0000" * 8) is True
    assert model_provider._is_empty_cohort_for_no_clicks("0100" * 8) is False
    assert model_provider._is_empty_cohort_for_no_clicks("0000" * 7 + "0100") is False
    assert model_provider._is_empty_cohort_for_no_clicks("1000" * 7 + "0100") is False


@pytest.mark.asyncio
async def test_cohort_model_skips_due_to_mismatch(
    gcs_storage_client, gcs_bucket, metrics_client, blob
):
    """Test that graceful failures due to various mismatched parameters."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-othermodel", interests="1" * model_provider._num_bits
    )
    assert result is None

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-othermodel", interests="1" * (model_provider._num_bits - 1)
    )
    assert result is None

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model",
        interests="1" * model_provider._num_bits,
        training_run_id="different-run-id",
    )
    assert result is None


@pytest.mark.asyncio
async def test_gcs_engagement_logs_error_for_large_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)

    await wait_until_model_is_updated(model_provider)

    max_size = settings.interest_cohort_model.gcs.max_size
    assert f"Blob '{large_blob.name}' size {max_size + 1} exceeds {max_size}" in caplog.text


@pytest.mark.asyncio
async def test_gcs_cohort_logs_error_for_missing_blob(
    gcs_storage_client, gcs_bucket, metrics_client, caplog, setting_environment
):
    """Test that the backend logs an error if the blob does not exist, outside 'stage'."""
    # Set the environment for each test case
    caplog.set_level(logging.INFO)
    create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)

    def expected_message_is_logged():
        # Filter log records to only those with the expected log level
        expected_level_name = "INFO" if setting_environment == "stage" else "ERROR"
        log_records = [
            record for record in caplog.records if record.levelname == expected_level_name
        ]
        # Assert that the expected message appears with the expected log level
        expected_message = "Blob 'contextual_ts/cohort_model_v2.safetensors' not found."
        return any(expected_message in record.message for record in log_records)

    # Ensure that this test runs quickly, by waiting only until the expected message is logged.
    await wait(until=expected_message_is_logged)

    assert expected_message_is_logged()


@pytest.mark.asyncio
async def test_gcs_cohort_model_metrics(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend records the correct metrics."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)
    # Check the last_updated gauge value shows that the data was updated just now.
    assert any(
        call[0][0] == "recommendation.ml.interest_cohort_model.last_updated"
        and 0 <= call[1]["value"] <= 10
        for call in metrics_client.gauge.call_args_list
    ), "The gauge recommendation.ml.interest_cohort_model.last_updated was not called with value between 0 and 10"
