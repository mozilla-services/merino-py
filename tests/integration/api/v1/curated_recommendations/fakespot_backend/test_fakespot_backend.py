"""Tests loading Fakespot products data from Google Cloud Storage."""

import asyncio
import json
import logging
import time

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Bucket
import orjson

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId
from merino.curated_recommendations.fakespot_backend.fakespot_backend import GcsFakespot
from merino.utils.synced_gcs_blob import SyncedGcsBlob
from tests.integration.api.conftest import fakespot_feed


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(
        settings.curated_recommendations.gcs.fakespot_bucket_name
    )
    yield bucket
    bucket.delete(force=True)


def create_gcs_fakespot(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> GcsFakespot:
    """Return an initialized GcsFakespot instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.curated_recommendations.gcs.fakespot.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.fakespot",
        max_size=settings.curated_recommendations.gcs.fakespot.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_recommendation_fakespot",
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GcsFakespot(
        synced_gcs_blob=synced_gcs_blob,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.fakespot",
    )


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.curated_recommendations.gcs.fakespot.blob_name)
    blob.upload_from_string(json.dumps(data))
    return blob


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with fakespot products data."""
    with open("tests/data/fakespot_products.json", "rb") as f:
        fakespot_products_json_data = orjson.loads(f.read())
    return create_blob(
        gcs_bucket,
        fakespot_products_json_data,
    )


@pytest.fixture
def large_blob(gcs_bucket):
    """Create a large blob in the fake GCS server."""
    return create_blob(
        gcs_bucket,
        "a" * (settings.curated_recommendations.gcs.fakespot.max_size + 1),
    )


async def wait_until_fakespot_is_updated(backend: GcsFakespot):
    """Wait for some time to pass to update fakespot."""
    max_wait_time_sec = 2
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if backend.update_count > 0:
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


@pytest.mark.asyncio
async def test_gcs_fakespot_returns_none_for_missing_keys(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that the backend returns None for keys not in the GCS blobs."""
    gcs_fakespot = create_gcs_fakespot(gcs_storage_client, gcs_bucket, metrics_client)
    assert gcs_fakespot.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_fakespot_fetches_data(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend fetches data from GCS and returns fakespot products data."""
    gcs_fakespot = create_gcs_fakespot(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_fakespot_is_updated(gcs_fakespot)

    assert gcs_fakespot.get(ScheduledSurfaceId.NEW_TAB_EN_US) == fakespot_feed()


@pytest.mark.asyncio
async def test_gcs_fakespot_logs_error_for_large_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    gcs_fakespot = create_gcs_fakespot(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)

    await wait_until_fakespot_is_updated(gcs_fakespot)

    max_size = settings.curated_recommendations.gcs.fakespot.max_size
    assert f"Blob '{large_blob.name}' size {max_size + 3} exceeds {max_size}" in caplog.text


@pytest.mark.asyncio
async def test_gcs_fakespot_metrics(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend records the correct metrics."""
    gcs_fakespot = create_gcs_fakespot(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_fakespot_is_updated(gcs_fakespot)

    # Verify the metrics are recorded correctly
    metrics_client.gauge.assert_any_call("recommendation.fakespot.size", value=blob.size)
    metrics_client.gauge.assert_any_call("recommendation.fakespot.count", value=8)
    metrics_client.timeit.assert_any_call("recommendation.fakespot.update.timing")
