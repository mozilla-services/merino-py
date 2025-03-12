"""Tests loading prior data from Google Cloud Storage."""

import asyncio
import json
import logging
import time

import pytest

from merino.configs import settings
from merino.curated_recommendations.prior_backends.gcs_prior import GcsPrior
from merino.curated_recommendations.prior_backends.protocol import Prior
from merino.utils.synced_gcs_blob import SyncedGcsBlob


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(settings.curated_recommendations.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def create_gcs_prior(gcs_storage_client, gcs_bucket, metrics_client) -> GcsPrior:
    """Return an initialized GcsPrior instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.curated_recommendations.gcs.prior.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.prior",
        max_size=settings.curated_recommendations.gcs.prior.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_recommendation_engagement",
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GcsPrior(synced_gcs_blob=synced_gcs_blob)


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.curated_recommendations.gcs.prior.blob_name)
    blob.upload_from_string(json.dumps(data))
    return blob


async def wait_until_prior_is_updated(backend: GcsPrior):
    """Wait for some time to pass to update prior."""
    max_wait_time_sec = 2
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if backend.update_count > 0:
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with region and global data."""
    return create_blob(
        gcs_bucket,
        [
            {
                "region": "US",
                "average_ctr_top2_items": 0.05,
                "impressions_per_item": 15000,
            },
            {
                "region": "CA",
                "average_ctr_top2_items": 0.04,
                "impressions_per_item": 10000,
            },
            {
                "average_ctr_top2_items": 0.03,
                "impressions_per_item": 8000,
            },
        ],
    )


@pytest.fixture
def large_blob(gcs_bucket):
    """Create a large blob in the fake GCS server."""
    return create_blob(
        gcs_bucket,
        "a" * (settings.curated_recommendations.gcs.prior.max_size + 1),
    )


@pytest.mark.asyncio
async def test_gcs_prior_returns_none_for_missing_keys(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that the backend returns None for keys not in the GCS blobs."""
    gcs_prior = create_gcs_prior(gcs_storage_client, gcs_bucket, metrics_client)
    assert gcs_prior.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_prior_fetches_data(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend fetches data from GCS and returns prior data."""
    gcs_prior = create_gcs_prior(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_prior_is_updated(gcs_prior)

    assert gcs_prior.get("US") == Prior(region="US", alpha=37.5, beta=750.0)
    # assert gcs_prior.get("US") == Prior(region="US", alpha=75.0, beta=1500.0)
    assert gcs_prior.get("CA") == Prior(region="CA", alpha=20.0, beta=500.0)
    #assert gcs_prior.get("CA") == Prior(region="CA", alpha=40.0, beta=1000.0)
    assert gcs_prior.get() == Prior(region=None, alpha=12.0, beta=400.0)
    # assert gcs_prior.get() == Prior(region=None, alpha=24.0, beta=800.0)


@pytest.mark.asyncio
async def test_gcs_prior_logs_error_for_large_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    gcs_prior = create_gcs_prior(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)

    await wait_until_prior_is_updated(gcs_prior)

    max_size = settings.curated_recommendations.gcs.prior.max_size
    assert f"Blob '{large_blob.name}' size {max_size+3} exceeds {max_size}" in caplog.text


@pytest.mark.asyncio
async def test_gcs_prior_metrics(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend records the correct metrics."""
    gcs_prior = create_gcs_prior(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_prior_is_updated(gcs_prior)

    # Verify the metrics are recorded correctly
    metrics_client.gauge.assert_any_call("recommendation.prior.size", value=blob.size)
    metrics_client.timeit.assert_any_call("recommendation.prior.update.timing")

    # Check the last_updated gauge value shows that the prior was updated just now.
    assert any(
        call[0][0] == "recommendation.prior.last_updated" and 0 <= call[1]["value"] <= 10
        for call in metrics_client.gauge.call_args_list
    ), "The gauge recommendation.prior.last_updated was not called with value between 0 and 10"
