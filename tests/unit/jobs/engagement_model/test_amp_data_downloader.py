"""Unit tests for engagement model AMP data downloader."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError

from merino.jobs.engagement_model.amp_data_downloader import EngagementDataDownloader


def test_download_by_advertiser():
    """Test downloading advertiser-level AMP engagement data."""
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
        data = downloader.download_by_advertiser()
        assert data == rows
        mock_client.query.assert_called_once()


def test_download_by_advertiser_raises_runtime_error_on_bigquery_failure():
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
            match="Failed to fetch advertiser-level AMP engagement data from BigQuery",
        ):
            downloader.download_by_advertiser()

        mock_client.query.assert_called_once()


def test_download_by_advertiser_skips_malformed_rows():
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
        data = downloader.download_by_advertiser()

        assert data == [
            {
                "advertiser": "mozilla",
                "impressions": 1000,
                "clicks": 22,
            }
        ]


def test_download_by_advertiser_returns_empty_list_when_no_rows():
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
        data = downloader.download_by_advertiser()

        assert data == []


def test_download_by_keyword():
    """Test downloading keyword-level AMP engagement data."""
    rows = [
        {
            "advertiser": "mozilla",
            "query": "firefox",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "query": "browser",
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
        data = downloader.download_by_keyword()
        assert data == rows
        mock_client.query.assert_called_once()


def test_download_by_keyword_raises_runtime_error_on_bigquery_failure():
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
            match="Failed to fetch keyword-level AMP engagement data from BigQuery",
        ):
            downloader.download_by_keyword()

        mock_client.query.assert_called_once()


def test_download_by_keyword_skips_malformed_rows():
    """Test that malformed rows are skipped."""
    rows = [
        {
            "advertiser": "mozilla",
            "query": "firefox",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "query": "browser",
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
        data = downloader.download_by_keyword()

        assert data == [
            {
                "advertiser": "mozilla",
                "query": "firefox",
                "impressions": 1000,
                "clicks": 22,
            }
        ]


def test_download_by_keyword_returns_empty_list_when_no_rows():
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
        data = downloader.download_by_keyword()

        assert data == []


def test_transform_by_advertiser_returns_advertiser_keyed_dict():
    """Test that advertiser rows are keyed by advertiser name."""
    data = [
        {"advertiser": "mozilla", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "impressions": 5666, "clicks": 0},
    ]
    result = EngagementDataDownloader.transform_by_advertiser(data)
    assert result == {
        "mozilla": {"advertiser": "mozilla", "impressions": 1000, "clicks": 22},
        "firefox": {"advertiser": "firefox", "impressions": 5666, "clicks": 0},
    }


def test_transform_by_advertiser_returns_empty_dict_for_empty_input():
    """Test that an empty input returns an empty dict."""
    assert EngagementDataDownloader.transform_by_advertiser([]) == {}


def test_aggregate_by_advertiser_sums_impressions_and_clicks():
    """Test that impressions and clicks are summed across all rows."""
    data = [
        {"advertiser": "mozilla", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "impressions": 5666, "clicks": 0},
    ]
    result = EngagementDataDownloader.aggregate_by_advertiser(data)
    assert result == {"impressions": 6666, "clicks": 22}


def test_aggregate_by_advertiser_returns_zeros_for_empty_input():
    """Test that an empty input returns zero totals."""
    assert EngagementDataDownloader.aggregate_by_advertiser([]) == {
        "impressions": 0,
        "clicks": 0,
    }


def test_transform_by_keyword_returns_advertiser_query_keyed_dict():
    """Test that keyword rows are keyed by advertiser/query with historical wrapper."""
    data = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "query": "browser", "impressions": 5666, "clicks": 0},
    ]
    result = EngagementDataDownloader.transform_by_keyword(data)
    assert result == {
        "mozilla/firefox": {"historical": {"impressions": 1000, "clicks": 22}},
        "firefox/browser": {"historical": {"impressions": 5666, "clicks": 0}},
    }


def test_transform_by_keyword_returns_empty_dict_for_empty_input():
    """Test that an empty input returns an empty dict."""
    assert EngagementDataDownloader.transform_by_keyword([]) == {}


def test_aggregate_by_keyword_sums_impressions_and_clicks():
    """Test that impressions and clicks are summed from the historical data."""
    transformed = {
        "mozilla/firefox": {"historical": {"impressions": 1000, "clicks": 22}},
        "firefox/browser": {"historical": {"impressions": 5666, "clicks": 0}},
    }
    result = EngagementDataDownloader.aggregate_by_keyword(transformed)
    assert result == {"impressions": 6666, "clicks": 22}


def test_aggregate_by_keyword_returns_zeros_for_empty_input():
    """Test that an empty input returns zero totals."""
    assert EngagementDataDownloader.aggregate_by_keyword({}) == {
        "impressions": 0,
        "clicks": 0,
    }
