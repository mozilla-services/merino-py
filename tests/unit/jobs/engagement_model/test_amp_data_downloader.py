"""Unit tests for engagement model AMP data downloader."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError

from merino.jobs.engagement_model.amp_data_downloader import EngagementDataDownloader


def test_fetch_keyword_rows_returns_parsed_rows():
    """Test that _fetch_keyword_rows parses BigQuery rows correctly."""
    rows = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "query": "browser", "impressions": 5666, "clicks": 0},
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
        data = downloader._fetch_keyword_rows("SELECT 1", "test")
        assert data == rows
        mock_client.query.assert_called_once_with("SELECT 1")


def test_fetch_keyword_rows_raises_runtime_error_on_bigquery_failure():
    """Test that a BigQuery failure is wrapped in RuntimeError with the given label."""
    mock_client = MagicMock()
    mock_client.query.side_effect = GoogleAPIError("BigQuery failed")

    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
        return_value=mock_client,
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")

        with pytest.raises(
            RuntimeError,
            match="Failed to fetch test keyword-level AMP engagement data from BigQuery",
        ):
            downloader._fetch_keyword_rows("SELECT 1", "test")


def test_fetch_keyword_rows_skips_malformed_rows():
    """Test that rows missing expected fields are skipped."""
    rows = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "query": "browser", "impressions": 5666},  # missing clicks
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
        data = downloader._fetch_keyword_rows("SELECT 1", "test")
        assert data == [
            {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22}
        ]


def test_fetch_keyword_rows_returns_empty_list_when_no_rows():
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
        assert downloader._fetch_keyword_rows("SELECT 1", "test") == []


def test_download_historical_data_by_keyword_delegates_to_helper():
    """Test that download_historical_data_by_keyword calls _fetch_keyword_rows with the historical query."""
    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")
        downloader._fetch_keyword_rows = MagicMock(return_value=[])
        downloader.download_historical_data_by_keyword()
        downloader._fetch_keyword_rows.assert_called_once_with(
            EngagementDataDownloader.KEYWORD_QUERY_HISTORICAL, "historical"
        )


def test_download_live_data_by_keyword_delegates_to_helper():
    """Test that download_live_data_by_keyword calls _fetch_keyword_rows with the live query."""
    with patch(
        "merino.jobs.engagement_model.amp_data_downloader.Client",
    ):
        downloader = EngagementDataDownloader(source_gcp_project="merino-test")
        downloader._fetch_keyword_rows = MagicMock(return_value=[])
        downloader.download_live_data_by_keyword()
        downloader._fetch_keyword_rows.assert_called_once_with(
            EngagementDataDownloader.KEYWORD_QUERY_LIVE, "live"
        )


def test_transform_by_keyword_with_historical_only():
    """Test that historical-only rows produce entries with only a historical key."""
    historical = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
        {"advertiser": "firefox", "query": "browser", "impressions": 5666, "clicks": 0},
    ]
    result = EngagementDataDownloader.transform_by_keyword(historical=historical, live=[])
    assert result == {
        "mozilla/firefox": {"historical": {"impressions": 1000, "clicks": 22}},
        "firefox/browser": {"historical": {"impressions": 5666, "clicks": 0}},
    }


def test_transform_by_keyword_with_live_only():
    """Test that live-only rows produce entries with only a live key."""
    live = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 500, "clicks": 10},
        {"advertiser": "firefox", "query": "browser", "impressions": 200, "clicks": 5},
    ]
    result = EngagementDataDownloader.transform_by_keyword(historical=[], live=live)
    assert result == {
        "mozilla/firefox": {"live": {"impressions": 500, "clicks": 10}},
        "firefox/browser": {"live": {"impressions": 200, "clicks": 5}},
    }


def test_transform_by_keyword_merges_matching_pairs():
    """Test that matching advertiser/query pairs from both datasets are merged."""
    historical = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
    ]
    live = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 500, "clicks": 10},
    ]
    result = EngagementDataDownloader.transform_by_keyword(historical=historical, live=live)
    assert result == {
        "mozilla/firefox": {
            "historical": {"impressions": 1000, "clicks": 22},
            "live": {"impressions": 500, "clicks": 10},
        }
    }


def test_transform_by_keyword_unions_non_matching_pairs():
    """Test that non-overlapping pairs appear with only their respective data source."""
    historical = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 1000, "clicks": 22},
    ]
    live = [
        {"advertiser": "firefox", "query": "browser", "impressions": 200, "clicks": 5},
    ]
    result = EngagementDataDownloader.transform_by_keyword(historical=historical, live=live)
    assert result == {
        "mozilla/firefox": {"historical": {"impressions": 1000, "clicks": 22}},
        "firefox/browser": {"live": {"impressions": 200, "clicks": 5}},
    }


def test_transform_by_keyword_returns_empty_dict_for_empty_inputs():
    """Test that empty historical and live inputs return an empty dict."""
    assert EngagementDataDownloader.transform_by_keyword(historical=[], live=[]) == {}


def test_aggregate_by_keyword_returns_zeros():
    """Test that aggregate_by_keyword returns zeros (not yet consumed)."""
    transformed = {
        "mozilla/firefox": {
            "historical": {"impressions": 1000, "clicks": 22},
            "live": {"impressions": 500, "clicks": 10},
        },
    }
    assert EngagementDataDownloader.aggregate_by_keyword(transformed) == {
        "impressions": 0,
        "clicks": 0,
    }


def test_aggregate_by_keyword_returns_zeros_for_empty_input():
    """Test that an empty input also returns zeros."""
    assert EngagementDataDownloader.aggregate_by_keyword({}) == {
        "impressions": 0,
        "clicks": 0,
    }
