"""Unit tests for engagement_model wikipedia_data_downloader."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError

from merino.jobs.engagement_model.wikipedia_data_downloader import (
    EngagementDataDownloader,
)


@pytest.mark.parametrize(
    ("mock_data", "expected_result"),
    [
        ([{"impressions": 321, "clicks": 123}], {"impressions": 321, "clicks": 123}),
        ([], {"impressions": 0, "clicks": 0}),
    ],
)
def test_download_wikipedia_data(
    mock_data: list[dict[str, int]],
    expected_result: dict[str, int],
) -> None:
    """Test Wikipedia engagement data is returned correctly."""
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = iter(mock_data)
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.wikipedia_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="test-merino")
        data = downloader.download_data()
        assert data == expected_result
        mock_client.query.assert_called_once()


def test_download_wikipedia_data_raises_runtime_error_on_bigquery_failure() -> None:
    """Test that a BigQuery failure is wrapped in RuntimeError."""
    mock_client = MagicMock()
    mock_client.query.side_effect = GoogleAPIError("BigQuery failed")

    with patch(
        "merino.jobs.engagement_model.wikipedia_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="test-merino")

        with pytest.raises(
            RuntimeError,
            match="Failed to fetch Wikipedia engagement data from BigQuery",
        ):
            downloader.download_data()

        mock_client.query.assert_called_once()


def test_download_wikipedia_data_raises_runtime_error_on_malformed_row() -> None:
    """Test that a malformed row raises RuntimeError."""
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.result.return_value = iter(
        [
            {
                "impressions": 321,
                # missing "clicks"
            }
        ]
    )
    mock_client.query.return_value = mock_query

    with patch(
        "merino.jobs.engagement_model.wikipedia_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="test-merino")

        with pytest.raises(
            RuntimeError,
            match="Wikipedia engagement data was missing expected fields",
        ):
            downloader.download_data()

        mock_client.query.assert_called_once()
