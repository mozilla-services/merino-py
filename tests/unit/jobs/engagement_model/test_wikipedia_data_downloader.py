"""Unit tests for engagement_model wikipedia_data_downloader."""

from unittest.mock import MagicMock, patch

import pytest

from merino.jobs.engagement_model.wikipedia_data_downloader import EngagementDataDownloader


@pytest.mark.parametrize(
    ("mock_data", "expected_result"),
    [
        ([{"impressions": 321, "clicks": 123}], {"impressions": 321, "clicks": 123}),
        ([], {"impressions": 0, "clicks": 0}),
    ],
)
def test_download_wikipedia_data(mock_data: dict, expected_result: dict) -> None:
    """Test no rows from BigQuery returns 0 impressions and clicks."""
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = iter(mock_data)
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.wikipedia_data_downloader.Client", return_value=mock_client
    ):
        downloader = EngagementDataDownloader(source_gcp_project="test-merino")
        data = downloader.download_data()
        assert data == expected_result
        mock_client.query.assert_called_once()
