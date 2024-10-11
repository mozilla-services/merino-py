"""Tests loading engagement data from Google Cloud Storage."""

import asyncio
import json
import logging
import time

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Bucket

from merino.config import settings
from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.engagement_backends.protocol import Engagement
from merino.utils.synced_gcs_blob import SyncedGcsBlob


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(settings.curated_recommendations.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def create_gcs_engagement(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> GcsEngagement:
    """Return an initialized GcsEngagement instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.curated_recommendations.gcs.engagement.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.engagement",
        max_size=settings.curated_recommendations.gcs.engagement.max_size,
        cron_interval_seconds=0.01,
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GcsEngagement(
        synced_gcs_blob=synced_gcs_blob,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.engagement",
    )


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.curated_recommendations.gcs.engagement.blob_name)
    blob.upload_from_string(json.dumps(data))
    time.sleep(1)
    return blob


async def wait_until_engagement_is_updated(backend: GcsEngagement):
    """Wait for some time to pass to update engagement."""
    max_wait_time_sec = 5
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if backend.update_count > 0:
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        [
            {"scheduled_corpus_item_id": "1A", "click_count": 30, "impression_count": 300},
            {"scheduled_corpus_item_id": "6A", "click_count": 40, "impression_count": 400},
            {
                "scheduled_corpus_item_id": "1A",
                "region": "US",
                "click_count": 3,
                "impression_count": 9,
            },
            {
                "scheduled_corpus_item_id": "6A",
                "region": "US",
                "click_count": 4,
                "impression_count": 9,
            },
        ],
    )


@pytest.fixture
def large_blob(gcs_bucket):
    """Create a large blob in the fake GCS server."""
    return create_blob(
        gcs_bucket,
        "a" * (settings.curated_recommendations.gcs.engagement.max_size + 1),
    )


@pytest.mark.asyncio
async def test_gcs_engagement_returns_none_for_missing_keys(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that the backend returns None for keys not in the GCS blobs."""
    gcs_engagement = create_gcs_engagement(gcs_storage_client, gcs_bucket, metrics_client)
    assert gcs_engagement.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_engagement_fetches_data(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend fetches data from GCS and returns engagement data."""
    gcs_engagement = create_gcs_engagement(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_engagement_is_updated(gcs_engagement)

    assert gcs_engagement.get("1A") == Engagement(
        scheduled_corpus_item_id="1A", click_count=30, impression_count=300
    )
    assert gcs_engagement.get("6A") == Engagement(
        scheduled_corpus_item_id="6A", click_count=40, impression_count=400
    )


@pytest.mark.asyncio
async def test_gcs_engagement_fetches_region_data(
    gcs_storage_client, gcs_bucket, metrics_client, blob
):
    """Test that the backend fetches data from GCS and returns engagement data."""
    gcs_engagement = create_gcs_engagement(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_engagement_is_updated(gcs_engagement)

    assert gcs_engagement.get("6A") == Engagement(
        scheduled_corpus_item_id="6A", click_count=40, impression_count=400
    )
    assert gcs_engagement.get("6A", "US") == Engagement(
        scheduled_corpus_item_id="6A", region="US", click_count=4, impression_count=9
    )

    # Fixture does not contain data for AU, so None should be returned.
    assert gcs_engagement.get("6A", "AU") is None


@pytest.mark.asyncio
async def test_gcs_engagement_logs_error_for_large_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    gcs_engagement = create_gcs_engagement(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)

    await wait_until_engagement_is_updated(gcs_engagement)

    max_size = settings.curated_recommendations.gcs.engagement.max_size
    assert f"Blob '{large_blob.name}' size {max_size+3} exceeds {max_size}" in caplog.text


@pytest.mark.asyncio
async def test_gcs_engagement_metrics(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend records the correct metrics."""
    gcs_engagement = create_gcs_engagement(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_engagement_is_updated(gcs_engagement)

    # Verify the metrics are recorded correctly
    metrics_client.gauge.assert_any_call("recommendation.engagement.size", value=blob.size)
    metrics_client.gauge.assert_any_call("recommendation.engagement.global.count", value=2)
    metrics_client.gauge.assert_any_call("recommendation.engagement.global.clicks", value=70)
    metrics_client.gauge.assert_any_call("recommendation.engagement.global.impressions", value=700)
    metrics_client.gauge.assert_any_call("recommendation.engagement.us.count", value=2)
    metrics_client.gauge.assert_any_call("recommendation.engagement.us.clicks", value=7)
    metrics_client.gauge.assert_any_call("recommendation.engagement.us.impressions", value=18)
    metrics_client.timeit.assert_any_call("recommendation.engagement.update.timing")

    # Check the last_updated gauge value shows that the engagement was updated just now.
    assert any(
        call[0][0] == "recommendation.engagement.last_updated" and 0 <= call[1]["value"] <= 10
        for call in metrics_client.gauge.call_args_list
    ), "The gauge recommendation.engagement.last_updated was not called with value between 0 and 10"
