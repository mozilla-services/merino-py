"""Unit tests for engagement model AMP data downloader."""

from unittest.mock import MagicMock, patch

from merino.jobs.engagement_model.amp_data_downloader import EngagementDataDownloader


def test_download_amp_data():
    """Test Download AMP engagement data."""
    rows = [
        {
            "advertiser": "mozilla",
            "suggestion_id": "88888",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "suggestion_id": "123456",
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
