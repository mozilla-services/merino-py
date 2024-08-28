"""Tests loading engagement data from Google Cloud Storage."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest
from aiodogstatsd import Client as StatsdClient
from freezegun import freeze_time
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from merino.config import settings
from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.engagement_backends.protocol import Engagement


@pytest.fixture(scope="module")
def gcs_container():
    """Set up a Docker container for the fake GCS server."""
    container = (
        DockerContainer("fsouza/fake-gcs-server:latest")
        .with_bind_ports(4443, 4443)
        .with_command("-scheme http")
    )
    container.start()

    # Wait until the server is up and running
    wait_for_logs(container, "server started", timeout=30)

    yield container
    container.stop()


@pytest.fixture(scope="module")
def gcs_client(gcs_container):
    """Create a Google Cloud Storage client connected to the fake GCS server."""
    client = Client(
        project=settings.curated_recommendations.gcs_engagement.gcp_project,
        credentials=AnonymousCredentials(),  # Use anonymous credentials to bypass auth
        client_options={
            "api_endpoint": "http://localhost:4443"
        },  # Point to the local fake GCS server
    )
    yield client


@pytest.fixture(scope="function")
def gcs_bucket(gcs_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_client.create_bucket(settings.curated_recommendations.gcs_engagement.bucket_name)
    yield bucket
    bucket.delete(force=True)


@pytest.fixture
def mock_metrics_client(mocker):
    """Return a mock aiodogstatsd Client instance."""
    metrics_client = mocker.Mock(spec=StatsdClient)
    metrics_client.timeit.return_value.__enter__ = lambda *args: None
    metrics_client.timeit.return_value.__exit__ = lambda *args: None
    return metrics_client


MAX_SIZE = 1024 * 1024


@pytest.fixture
def gcs_engagement(gcs_client, gcs_bucket, mock_metrics_client):
    """Return a GcsEngagement instance using the fake GCS server."""
    return GcsEngagement(
        storage_client=gcs_client,
        metrics_client=mock_metrics_client,
        bucket_name=gcs_bucket.name,
        blob_prefix=settings.curated_recommendations.gcs_engagement.blob_prefix,
        max_size=settings.curated_recommendations.gcs_engagement.max_size,
        cron_interval_seconds=0.01,
    )


def create_blob(bucket, updated_at, data):
    """Create a blob with a given updated_at timestamp and data."""
    datetime_str = updated_at.strftime("%Y%m%d%H%M")
    blob_name = f"newtab-merino-exports/engagement_{datetime_str}.json"
    with freeze_time(updated_at):
        blob = bucket.blob(blob_name)
        blob.upload_from_string(json.dumps(data))
        time.sleep(1)
    return blob


@pytest.fixture
def blob_20min_ago(gcs_bucket):
    """Create a blob from 20 minutes ago."""
    datetime_20min_ago = datetime.now(timezone.utc) - timedelta(minutes=20)
    return create_blob(
        gcs_bucket,
        datetime_20min_ago,
        [
            {"scheduled_corpus_item_id": "12345", "click_count": 10, "impression_count": 100},
            {"scheduled_corpus_item_id": "67890", "click_count": 20, "impression_count": 200},
        ],
    )


@pytest.fixture
def blob_5min_ago(gcs_bucket):
    """Create a blob from 5 minutes ago."""
    datetime_5min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    return create_blob(
        gcs_bucket,
        datetime_5min_ago,
        [
            {"scheduled_corpus_item_id": "12345", "click_count": 30, "impression_count": 300},
            {"scheduled_corpus_item_id": "67890", "click_count": 40, "impression_count": 400},
        ],
    )


@pytest.fixture
def large_blob_1min_ago(gcs_bucket):
    """Create a large blob from 1 minute ago in the fake GCS server."""
    datetime_1min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    return create_blob(
        gcs_bucket,
        datetime_1min_ago,
        "a" * (settings.curated_recommendations.gcs_engagement.max_size + 1),
    )


@pytest.mark.asyncio
async def test_gcs_engagement_returns_zero_for_missing_keys(gcs_engagement):
    """Test that the backend returns None for keys not in the GCS blobs."""
    assert gcs_engagement.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_engagement_fetches_data(gcs_engagement, blob_20min_ago, blob_5min_ago):
    """Test that the backend fetches data from GCS and returns engagement data."""
    gcs_engagement.initialize()
    await asyncio.sleep(0.02)  # Allow the cron job to fetch data.

    assert gcs_engagement.get("12345") == Engagement(
        scheduled_corpus_item_id="12345", click_count=30, impression_count=300
    )
    assert gcs_engagement.get("67890") == Engagement(
        scheduled_corpus_item_id="67890", click_count=40, impression_count=400
    )


@pytest.mark.asyncio
async def test_gcs_engagement_logs_error_for_large_blob(
    gcs_engagement, large_blob_1min_ago, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    caplog.set_level(logging.ERROR)

    gcs_engagement.initialize()
    await asyncio.sleep(0.01)  # Allow the cron job to fetch data.

    assert "Curated recommendations engagement size 1000003 exceeds 1000000" in caplog.text


@pytest.mark.asyncio
async def test_gcs_engagement_metrics(gcs_engagement, mock_metrics_client, blob_5min_ago):
    """Test that the backend records the correct metrics."""
    gcs_engagement.initialize()
    await asyncio.sleep(0.1)  # Give the cron job time to run

    # Verify the metrics are recorded correctly
    mock_metrics_client.gauge.assert_any_call(
        "recommendation.engagement.size", value=blob_5min_ago.size
    )
    mock_metrics_client.gauge.assert_any_call("recommendation.engagement.count", value=2)
    mock_metrics_client.timeit.assert_any_call("recommendation.engagement.update.timing")

    # Check the last_updated gauge value shows that the engagement was updated just now.
    assert any(
        call[0][0] == "recommendation.engagement.last_updated" and 0 <= call[1]["value"] <= 10
        for call in mock_metrics_client.gauge.call_args_list
    ), "The gauge recommendation.engagement.last_updated was not called with value between 0 and 10"
