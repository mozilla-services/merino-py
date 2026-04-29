"""Unit tests for engagement_model CLI."""

import json
from unittest.mock import MagicMock, patch

from merino.jobs.engagement_model import upload_engagement_data


def test_upload_engagement_data_success() -> None:
    """Test engagement data is fetched, transformed, and uploaded to GCS."""
    amp_keyword_historical = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 100, "clicks": 5},
        {"advertiser": "firefox", "query": "browser", "impressions": 200, "clicks": 10},
    ]
    amp_keyword_live = [
        {"advertiser": "mozilla", "query": "firefox", "impressions": 50, "clicks": 3},
        {"advertiser": "chrome", "query": "search", "impressions": 80, "clicks": 2},
    ]
    wiki_data = {"impressions": 300, "clicks": 20}

    transformed_amp_data = {
        "mozilla/firefox": {
            "historical": {"impressions": 100, "clicks": 5},
            "live": {"impressions": 50, "clicks": 3},
        },
        "firefox/browser": {"historical": {"impressions": 200, "clicks": 10}},
        "chrome/search": {"live": {"impressions": 80, "clicks": 2}},
    }
    aggregated_amp_data = {"impressions": 0, "clicks": 0}

    mock_amp_downloader = MagicMock()
    mock_amp_downloader.download_historical_data.return_value = amp_keyword_historical
    mock_amp_downloader.download_live_data.return_value = amp_keyword_live
    mock_amp_downloader.transform_data.return_value = transformed_amp_data
    mock_amp_downloader.aggregate_data.return_value = aggregated_amp_data

    mock_wiki_downloader = MagicMock()
    mock_wiki_downloader.download_data.return_value = wiki_data

    mock_uploader = MagicMock()

    mock_settings = MagicMock()
    mock_settings.engagement.gcs_bq_project = "test-bq-project"
    mock_settings.engagement.gcs_storage_bucket = "test-bucket"
    mock_settings.engagement.gcs_storage_project = "test-storage-project"

    mock_datetime = MagicMock()
    mock_datetime.now.return_value.strftime.return_value = "20260316120000"

    with (
        patch("merino.jobs.engagement_model.settings", mock_settings),
        patch(
            "merino.jobs.engagement_model.AMPDownloader",
            return_value=mock_amp_downloader,
        ) as mock_amp_cls,
        patch(
            "merino.jobs.engagement_model.WikiDownloader",
            return_value=mock_wiki_downloader,
        ) as mock_wiki_cls,
        patch(
            "merino.jobs.engagement_model.GcsUploader",
            return_value=mock_uploader,
        ) as mock_uploader_cls,
        patch("merino.jobs.engagement_model.datetime", mock_datetime),
    ):
        upload_engagement_data()

    mock_amp_cls.assert_called_once_with("test-bq-project")
    mock_wiki_cls.assert_called_once_with("test-bq-project")
    mock_uploader_cls.assert_called_once_with(
        destination_gcp_project="test-storage-project",
        destination_bucket_name="test-bucket",
        destination_cdn_hostname="",
    )

    mock_amp_downloader.download_historical_data.assert_called_once()
    mock_amp_downloader.download_live_data.assert_called_once()
    mock_amp_downloader.transform_data.assert_called_once_with(
        historical=amp_keyword_historical,
        live=amp_keyword_live,
    )
    mock_amp_downloader.aggregate_data.assert_called_once_with(transformed_amp_data)
    mock_wiki_downloader.download_data.assert_called_once()

    expected_keyword_payload = {
        "amp": transformed_amp_data,
        "wiki_aggregated": {"impressions": 300, "clicks": 20},
        "amp_aggregated": aggregated_amp_data,
    }
    expected_keyword_content = json.dumps(expected_keyword_payload, indent=2)

    assert mock_uploader.upload_content.call_count == 2
    mock_uploader.upload_content.assert_any_call(
        content=expected_keyword_content,
        destination_name="suggest-merino-exports/engagement/keyword/20260316120000.json",
        content_type="application/json",
        forced_upload=True,
    )
    mock_uploader.upload_content.assert_any_call(
        content=expected_keyword_content,
        destination_name="suggest-merino-exports/engagement/keyword/latest.json",
        content_type="application/json",
        forced_upload=True,
    )


def test_upload_engagement_data_logs_error_on_keyword_download_failure() -> None:
    """Test engagement pipeline errors are logged when keyword download fails."""
    mock_settings = MagicMock()
    mock_settings.engagement.gcs_bq_project = "test-bq-project"
    mock_settings.engagement.gcs_storage_bucket = "test-bucket"
    mock_settings.engagement.gcs_storage_project = "test-storage-project"

    mock_amp_downloader = MagicMock()
    mock_amp_downloader.download_historical_data.side_effect = RuntimeError("BigQuery failed")

    mock_wiki_downloader = MagicMock()

    with (
        patch("merino.jobs.engagement_model.settings", mock_settings),
        patch(
            "merino.jobs.engagement_model.AMPDownloader",
            return_value=mock_amp_downloader,
        ),
        patch(
            "merino.jobs.engagement_model.WikiDownloader",
            return_value=mock_wiki_downloader,
        ),
        patch("merino.jobs.engagement_model.logger") as mock_logger,
    ):
        upload_engagement_data()

    mock_logger.error.assert_called_once()
    args, kwargs = mock_logger.error.call_args

    assert args[0] == "Engagement data pipeline failed: %s: %s"
    assert args[1] == RuntimeError.__name__
    assert "BigQuery failed" in args[2]
    assert kwargs["exc_info"] is True
