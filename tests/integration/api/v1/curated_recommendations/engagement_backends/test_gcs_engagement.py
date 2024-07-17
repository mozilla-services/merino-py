"""Tests loading engagement data from Google Cloud Storage."""

import json
import logging
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Blob, Bucket

from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.engagement_backends.protocol import Engagement


@pytest.fixture
def mock_gcs_client():
    """Return a mock GCS Client instance"""
    return MagicMock(spec=Client)


@pytest.fixture
def mock_gcs_bucket(mock_gcs_client):
    """Return a mock GCS Bucket instance"""
    bucket = MagicMock(spec=Bucket)
    mock_gcs_client.bucket.return_value = bucket
    return bucket


@pytest.fixture
def mock_gcs_blob(mock_gcs_bucket):
    """Return a mock GCS Blob instance"""
    blob = MagicMock(spec=Blob)
    mock_gcs_bucket.blob.return_value = blob
    return blob


@pytest.fixture
def mock_metrics_client(mocker):
    """Return a mock aiodogstatsd Client instance"""
    metrics_client = mocker.Mock(spec=StatsdClient)
    metrics_client.timeit.return_value.__enter__ = lambda *args: None
    metrics_client.timeit.return_value.__exit__ = lambda *args: None
    return metrics_client


@pytest.fixture(name="gcs_engagement")
def mock_gcs_engagement(mock_gcs_client, mock_metrics_client):
    """Return a mock GCS Engagement instance"""
    gcs_engagement = GcsEngagement(
        storage_client=mock_gcs_client,
        metrics_client=mock_metrics_client,
        bucket_name="test-bucket",
        blob_name="test-blob",
        max_size=1024 * 1024,
        thread_sleep_period=timedelta(milliseconds=10),
    )
    yield gcs_engagement
    gcs_engagement.shutdown()


def test_gcs_engagement_backend_return_zero_for_missing_keys(gcs_engagement):
    """Test that the backend returns 0 clicks and impressions for keys not in the fixture"""
    assert gcs_engagement["missing_key"] == Engagement(
        scheduled_corpus_item_id="missing_key", clicks=0, impressions=0
    )


def test_gcs_engagement_backend_fetches_data(gcs_engagement, mock_gcs_blob):
    """Test that the backend fetches data from GCS and returns engagement data"""
    engagement_data = [
        {"scheduled_corpus_item_id": "12345", "clicks": 10, "impressions": 100},
        {"scheduled_corpus_item_id": "67890", "clicks": 20, "impressions": 200},
    ]
    mock_gcs_blob.download_as_text.return_value = json.dumps(engagement_data)
    mock_gcs_blob.size = 512
    mock_gcs_blob.updated = datetime(2024, 1, 1, 0, 0, 0)

    gcs_engagement.initialize()
    time.sleep(0.02)  # Allow the background thread to fetch data.

    assert gcs_engagement["12345"] == Engagement(
        scheduled_corpus_item_id="12345", clicks=10, impressions=100
    )
    assert gcs_engagement["67890"] == Engagement(
        scheduled_corpus_item_id="67890", clicks=20, impressions=200
    )


def test_gcs_engagement_backend_logs_error_for_large_blob(gcs_engagement, mock_gcs_blob, caplog):
    """Test that the backend logs an error if the blob size exceeds the max size"""
    caplog.set_level(logging.ERROR)
    mock_gcs_blob.size = 1024 * 1024 + 1  # 1 byte over the limit
    mock_gcs_blob.updated = datetime(2024, 1, 1, 0, 0, 0)

    gcs_engagement.initialize()
    time.sleep(0.01)  # Allow the background thread to fetch data.

    assert "Curated recommendations engagement size 1048577 > 1048576" in caplog.text


def test_gcs_engagement_backend_download_count(mock_gcs_blob, mock_gcs_client):
    """Test that the backend periodically updates engagement from GCS

    This test uses actual time because freezegun cannot freeze time in threads:
    https://github.com/spulec/freezegun/issues/307
    Alternatively, the 'time-machine' library does support mocking time in threads.
    """
    gcs_engagement = GcsEngagement(
        storage_client=mock_gcs_client,
        metrics_client=MagicMock(spec=StatsdClient),
        bucket_name="test-bucket",
        blob_name="test-blob",
        max_size=1024 * 1024,
        thread_sleep_period=timedelta(milliseconds=1),
        gcs_check_interval=timedelta(milliseconds=10),  # A short interval keeps this test fast.
    )

    start_time = datetime.now()
    mock_gcs_blob.updated = start_time
    mock_gcs_blob.download_as_text.return_value = json.dumps([])
    mock_gcs_blob.size = 512

    gcs_engagement.initialize()  # Start the background task

    # Sleep for a set period of time, while periodically increasing the mock 'updated' attribute.
    expected_downloads = 3
    update_period = timedelta(milliseconds=100)  # Time between simulated updates to the blob
    for i in range(expected_downloads):
        mock_gcs_blob.updated = start_time + (i * update_period)
        time.sleep(update_period.total_seconds())

    assert mock_gcs_blob.download_as_text.call_count == expected_downloads

    gcs_engagement.shutdown()


def test_gcs_engagement_metrics(gcs_engagement, mock_gcs_blob, mock_metrics_client):
    """Test that the backend records the correct metrics."""
    engagement_data = [
        {"scheduled_corpus_item_id": "12345", "clicks": 10, "impressions": 100},
        {"scheduled_corpus_item_id": "67890", "clicks": 20, "impressions": 200},
    ]
    mock_gcs_blob.download_as_text.return_value = json.dumps(engagement_data)
    mock_gcs_blob.size = 512
    mock_gcs_blob.updated = datetime.now()

    gcs_engagement.initialize()
    time.sleep(0.02)  # Allow the background thread to fetch data.

    # Verify the metrics are recorded correctly
    mock_metrics_client.gauge.assert_any_call("recommendation.engagement.size", value=512)
    mock_metrics_client.gauge.assert_any_call("recommendation.engagement.count", value=2)
    mock_metrics_client.timeit.assert_any_call("recommendation.engagement.update.timing")

    # Check the last_updated gauge value is between 0 and 1
    assert any(
        call[0][0] == "recommendation.engagement.last_updated" and 0 <= call[1]["value"] <= 1
        for call in mock_metrics_client.gauge.call_args_list
    ), "The gauge recommendation.engagement.last_updated was not called with value between 0 and 1"
