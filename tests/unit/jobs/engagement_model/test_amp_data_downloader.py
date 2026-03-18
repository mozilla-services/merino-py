"""Unit tests for engagement model AMP data downloader."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError

from merino.jobs.engagement_model.amp_data_downloader import EngagementDataDownloader


def test_download_amp_data():
    """Test downloading AMP engagement data."""
    rows = [
        {
            "advertiser": "mozilla",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "impressions": 5666,
            "clicks": 0,
        },
    ]

    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = rows
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")
        data = downloader.download_data()
        assert data == rows
        mock_client.query.assert_called_once()


def test_download_amp_data_raises_runtime_error_on_bigquery_failure():
    """Test that a BigQuery failure is wrapped in RuntimeError."""
    mock_client = MagicMock()
    mock_client.query.side_effect = GoogleAPIError("BigQuery failed")

    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")

        with pytest.raises(
            RuntimeError,
            match="Failed to fetch AMP engagement data from BigQuery",
        ):
            downloader.download_data()

        mock_client.query.assert_called_once()


def test_download_amp_data_skips_malformed_rows():
    """Test that malformed rows are skipped."""
    rows = [
        {
            "advertiser": "mozilla",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "impressions": 5666,
            # missing clicks
        },
    ]

    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = rows
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")
        data = downloader.download_data()

        assert data == [
            {
                "advertiser": "mozilla",
                "impressions": 1000,
                "clicks": 22,
            }
        ]


def test_download_amp_data_returns_empty_list_when_no_rows():
    """Test that an empty result set returns an empty list."""
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = []
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")
        data = downloader.download_data()

        assert data == []
