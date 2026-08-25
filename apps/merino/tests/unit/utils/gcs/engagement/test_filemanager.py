# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the EngagementFilemanager module."""

import json

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from merino.providers.suggest.adm.backends.protocol import KeywordEntry, KeywordMetrics
from merino.utils.gcs.engagement.filemanager import (
    EngagementData,
    EngagementFilemanager,
)

GCS_BUCKET = "test-bucket"
BLOB_NAME = "suggest-merino-exports/engagement/keyword/latest.json"

SAMPLE_ENGAGEMENT_JSON = json.dumps(
    {
        "amp": {
            "mozilla/firefox": {
                "live": {"impressions": 3333, "clicks": 88},
                "historical": {"impressions": 6666, "clicks": 333},
            },
        },
        "wiki_aggregated": {"impressions": 2935973, "clicks": 2325},
        "amp_aggregated": {"impressions": 463225, "clicks": 5878},
    }
)


@pytest.fixture(name="filemanager")
def fixture_filemanager() -> EngagementFilemanager:
    """Return a fresh EngagementFilemanager instance for test."""
    return EngagementFilemanager(gcs_bucket_path=GCS_BUCKET, blob_name=BLOB_NAME)


@pytest.fixture(name="mock_blob")
def fixture_mock_blob(mocker: MockerFixture):
    """Return a mock gcloud.aio.storage Blob with engagement data."""
    blob = mocker.AsyncMock()
    blob.download = mocker.AsyncMock(return_value=SAMPLE_ENGAGEMENT_JSON.encode())
    return blob


@pytest.fixture(name="mock_bucket")
def fixture_mock_bucket(mocker: MockerFixture, mock_blob):
    """Return a mock gcloud.aio.storage Bucket for engagement data."""
    bucket = mocker.AsyncMock()
    bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)
    return bucket


def test_get_bucket_lazily_creates_client_and_bucket(
    mocker: MockerFixture,
    filemanager: EngagementFilemanager,
    mock_bucket,
) -> None:
    """Test that get_bucket() creates the GCS client and Bucket on first call."""
    mock_storage_cls = mocker.patch("merino.utils.gcs.engagement.filemanager.get_storage_client")
    mocker.patch("merino.utils.gcs.engagement.filemanager.Bucket", return_value=mock_bucket)

    assert filemanager.gcs_client is None
    assert filemanager.bucket is None

    bucket = filemanager.get_bucket()

    mock_storage_cls.assert_called_once()
    assert bucket is mock_bucket
    assert filemanager.bucket is mock_bucket


def test_get_bucket_returns_cached_bucket(
    mocker: MockerFixture,
    filemanager: EngagementFilemanager,
    mock_bucket,
) -> None:
    """Test that get_bucket() returns the cached Bucket without recreating the client."""
    filemanager.bucket = mock_bucket
    mock_storage_cls = mocker.patch("merino.utils.gcs.engagement.filemanager.Storage")

    bucket = filemanager.get_bucket()

    mock_storage_cls.assert_not_called()
    assert bucket is mock_bucket


@pytest.mark.asyncio
async def test_get_file_success(
    mocker: MockerFixture,
    filemanager: EngagementFilemanager,
    mock_bucket,
    mock_blob,
) -> None:
    """Test that get_file() downloads the blob and returns a full EngagementData instance."""
    mocker.patch("merino.utils.gcs.engagement.filemanager.Storage")
    mocker.patch("merino.utils.gcs.engagement.filemanager.Bucket", return_value=mock_bucket)

    result = await filemanager.get_file()

    mock_bucket.get_blob.assert_called_once_with(BLOB_NAME)
    mock_blob.download.assert_called_once()
    assert result is not None
    assert isinstance(result, EngagementData)
    assert isinstance(result.amp["mozilla/firefox"], KeywordEntry)
    assert isinstance(result.amp["mozilla/firefox"].live, KeywordMetrics)
    assert result.amp["mozilla/firefox"].live is not None
    assert result.amp["mozilla/firefox"].live.impressions == 3333
    assert result.amp["mozilla/firefox"].live.clicks == 88
    assert result.amp["mozilla/firefox"].historical is not None
    assert result.amp["mozilla/firefox"].historical.impressions == 6666
    assert result.amp["mozilla/firefox"].historical.clicks == 333
    assert result.amp_aggregated["impressions"] == 463225
    assert result.wiki_aggregated["clicks"] == 2325


@pytest.mark.asyncio
async def test_get_file_json_decode_error(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    filemanager: EngagementFilemanager,
    mock_bucket,
    mock_blob,
) -> None:
    """Test that get_file() returns None and logs an error on invalid JSON."""
    mock_blob.download.return_value = b"not valid json {"
    mocker.patch("merino.utils.gcs.engagement.filemanager.Storage")
    mocker.patch("merino.utils.gcs.engagement.filemanager.Bucket", return_value=mock_bucket)

    result = await filemanager.get_file()

    assert result is None
    assert any("Failed to decode engagement data JSON" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_file_gcs_exception(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    filemanager: EngagementFilemanager,
    mock_bucket,
) -> None:
    """Test that get_file() returns None and logs an error when GCS raises an exception."""
    mock_bucket.get_blob.side_effect = Exception("GCS timeout")
    mocker.patch("merino.utils.gcs.engagement.filemanager.Storage")
    mocker.patch("merino.utils.gcs.engagement.filemanager.Bucket", return_value=mock_bucket)

    result = await filemanager.get_file()

    assert result is None
    assert any("GCS timeout" in r.message for r in caplog.records)


def test_keyword_entry_requires_at_least_one_metrics_window() -> None:
    """Test that KeywordEntry raises if both live and historical are absent."""
    with pytest.raises(ValidationError):
        KeywordEntry()
