"""Unit test to upload engagement model data."""

import json
from unittest.mock import MagicMock, patch, call

import freezegun

from merino.jobs.engagement_model import upload_engagement_data


@freezegun.freeze_time("2026-03-10 12:34:56")
def test_gcs_uploader() -> None:
    """Test gcs uploader aggregates and uploads data correctly."""
    mock_uploader = MagicMock()
    mock_client = MagicMock()
    amp_data = [
        {
            "advertiser": "mozilla",
            "suggestion_id": "88888",
            "match_type": "firefox-suggest",
            "impressions": 1000,
            "clicks": 22,
        },
        {
            "advertiser": "firefox",
            "suggestion_id": "123456",
            "match_type": "best-match",
            "impressions": 5666,
            "clicks": 0,
        },
    ]
    amp_aggregated = {"impressions": 6666, "clicks": 22}
    wiki_data = {"impressions": 321, "clicks": 123}
    with (
        patch("merino.jobs.engagement_model.GcsUploader", return_value=mock_uploader),
        patch(
            "merino.jobs.engagement_model.amp_data_downloader.Client",
            return_value=mock_client,
        ),
        patch(
            "merino.jobs.engagement_model.wikipedia_data_downloader.Client",
            return_value=mock_client,
        ),
        patch(
            "merino.jobs.engagement_model.amp_data_downloader.EngagementDataDownloader.download_data",
            return_value=amp_data,
        ),
        patch(
            "merino.jobs.engagement_model.wikipedia_data_downloader.EngagementDataDownloader.download_data",
            return_value=wiki_data,
        ),
    ):
        upload_engagement_data()

        expected_data = json.dumps(
            {"amp": amp_data, "wiki_aggregated": wiki_data, "amp_aggregated": amp_aggregated},
            indent=2,
        )
        expected_destination_name = "suggest-merino-exports/engagement/20260310123456.json"
        expected_latest_name = "suggest-merino-exports/engagement/latest.json"

        assert mock_uploader.upload_content.call_count == 2
        mock_uploader.upload_content.assert_has_calls(
            [
                call(
                    content=expected_data,
                    destination_name=expected_destination_name,
                    content_type="application/json",
                    forced_upload=True,
                ),
                call(
                    content=expected_data,
                    destination_name=expected_latest_name,
                    content_type="application/json",
                    forced_upload=True,
                ),
            ]
        )
