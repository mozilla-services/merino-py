"""Tests loading engagement data from Google Cloud Storage."""

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Blob, Bucket

from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.engagement_backends.protocol import Engagement

import asyncio


@pytest.fixture
def mock_gcs_blobs():
    """Return a list of mock GCS Blob instances"""
    blob1 = MagicMock(spec=Blob)
    blob1.name = "newtab-merino-exports/engagement_202408211600.json"
    blob1.size = 512
    blob1.updated = datetime(2024, 8, 21, 16, 0, 0, tzinfo=timezone.utc)
    blob1.download_as_text.return_value = json.dumps(
        [
            {"scheduled_corpus_item_id": "12345", "click_count": 10, "impression_count": 100},
            {"scheduled_corpus_item_id": "67890", "click_count": 20, "impression_count": 200},
        ]
    )

    blob2 = MagicMock(spec=Blob)
    blob2.name = "newtab-merino-exports/engagement_202408211700.json"
    blob2.size = 1024
    blob2.updated = datetime(2024, 8, 21, 17, 0, 0, tzinfo=timezone.utc)
    blob2.download_as_text.return_value = json.dumps(
        [
            {"scheduled_corpus_item_id": "12345", "click_count": 30, "impression_count": 300},
            {"scheduled_corpus_item_id": "67890", "click_count": 40, "impression_count": 400},
        ]
    )

    return [blob1, blob2]


@pytest.fixture
def mock_gcs_bucket(mock_gcs_blobs):
    """Return a mock GCS Bucket instance with blobs preset"""
    bucket = MagicMock(spec=Bucket)
    bucket.list_blobs.return_value = mock_gcs_blobs
    return bucket


@pytest.fixture
def mock_gcs_client(mock_gcs_bucket):
    """Return a mock GCS Client instance"""
    client = MagicMock(spec=Client)
    client.bucket.return_value = mock_gcs_bucket
    return client


@pytest.fixture
def mock_metrics_client(mocker):
    """Return a mock aiodogstatsd Client instance"""
    metrics_client = mocker.Mock(spec=StatsdClient)
    metrics_client.timeit.return_value.__enter__ = lambda *args: None
    metrics_client.timeit.return_value.__exit__ = lambda *args: None
    return metrics_client


@pytest.fixture(name="gcs_engagement")
def mock_gcs_engagement(mock_gcs_client, mock_metrics_client) -> GcsEngagement:
    """Return a mock GCS Engagement instance"""
    return GcsEngagement(
        storage_client=mock_gcs_client,
        metrics_client=mock_metrics_client,
        bucket_name="test-bucket",
        blob_prefix="newtab-merino-exports/engagement_",
        max_size=1024 * 1024,
        cron_interval_seconds=0.01,  # Short interval ensures tests execute quickly.
    )


@pytest.mark.asyncio
async def test_gcs_engagement_returns_zero_for_missing_keys(gcs_engagement):
    """Test that the backend returns None for keys not in the fixture"""
    assert gcs_engagement.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_engagement_fetches_data(gcs_engagement):
    """Test that the backend fetches data from GCS and returns engagement data"""
    gcs_engagement.initialize()
    await asyncio.sleep(0.02)  # Allow the cron job to fetch data.

    assert gcs_engagement.get("12345") == Engagement(
        scheduled_corpus_item_id="12345", click_count=30, impression_count=300
    )
    assert gcs_engagement.get("67890") == Engagement(
        scheduled_corpus_item_id="67890", click_count=40, impression_count=400
    )


@pytest.mark.asyncio
async def test_gcs_engagement_logs_error_for_large_blob(gcs_engagement, mock_gcs_blobs, caplog):
    """Test that the backend logs an error if the blob size exceeds the max size"""
    caplog.set_level(logging.ERROR)
    mock_gcs_blobs[1].size = 1024 * 1024 + 1  # 1 byte over the limit

    gcs_engagement.initialize()
    await asyncio.sleep(0.01)  # Allow the cron job to fetch data.

    assert "Curated recommendations engagement size 1048577 exceeds 1048576" in caplog.text


@pytest.mark.asyncio
async def test_gcs_engagement_download_count(gcs_engagement, mock_gcs_blobs):
    """Test that the backend periodically updates engagement from GCS"""
    start_time = datetime.now(timezone.utc)
    mock_gcs_blobs[0].updated = start_time

    gcs_engagement.initialize()  # Start the cron job

    # Simulate time progression and updates
    expected_downloads = 3
    update_period = timedelta(milliseconds=100)  # Time between simulated updates to the blob
    for i in range(expected_downloads):
        mock_gcs_blobs[0].updated = start_time + (i * update_period)
        await asyncio.sleep(update_period.total_seconds())

    assert mock_gcs_blobs[0].download_as_text.call_count == expected_downloads


@pytest.mark.asyncio
async def test_gcs_engagement_metrics(gcs_engagement, mock_metrics_client, mock_gcs_blobs):
    """Test that the backend records the correct metrics."""
    mock_gcs_blobs[1].updated = datetime.now(timezone.utc)

    gcs_engagement.initialize()
    await asyncio.sleep(0.1)  # Give the cron job time to run

    # Verify the metrics are recorded correctly
    mock_metrics_client.gauge.assert_any_call("recommendation.engagement.size", value=1024)
    mock_metrics_client.gauge.assert_any_call("recommendation.engagement.count", value=2)
    mock_metrics_client.timeit.assert_any_call("recommendation.engagement.update.timing")

    # Check the last_updated gauge value shows that the engagement was updated just now.
    assert any(
        call[0][0] == "recommendation.engagement.last_updated" and 0 <= call[1]["value"] <= 1
        for call in mock_metrics_client.gauge.call_args_list
    ), "The gauge recommendation.engagement.last_updated was not called with value between 0 and 1"
