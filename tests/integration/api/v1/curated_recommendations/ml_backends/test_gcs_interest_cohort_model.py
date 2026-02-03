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
        model_id="inferred-v3-model", interests="1" * model_provider._num_bits
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

    # Test specific expected result for the v2 model, which has cohort of 1 for
    # a no clicks cohort. This test can be adjusted when the model is updated.
    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model", interests="1000" * 8
    )
    assert result == 1
    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model", interests="0000" * 8
    )
    assert result == 1


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
    test_in = interests_in[-model_provider._num_bits :]
    test_out = normalized_out[-model_provider._num_bits :]

    result = model_provider._normalize_interests(test_in)
    assert result == test_out


@pytest.mark.asyncio
async def test_normalize_interests_raises_on_wrong_length(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that _normalize_interests rejects strings of incorrect length."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    assert model_provider._normalize_interests("0" * (model_provider._num_bits - 1)) is None


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
