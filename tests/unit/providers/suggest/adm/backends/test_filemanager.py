# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the ADM filemanager module."""

import json

import pytest
from pytest_mock import MockerFixture

from merino.providers.suggest.adm.backends.filemanager import ADMFilemanager

GCS_BUCKET = "test-bucket"
BLOB_NAME = "suggest-merino-exports/engagement/latest.json"

SAMPLE_ENGAGEMENT_JSON = json.dumps(
    {
        "amp": {
            "1-800 flowers": {"advertiser": "1-800 flowers", "impressions": 2803, "clicks": 10},
            "aliexpress": {"advertiser": "aliexpress", "impressions": 1449, "clicks": 102},
        },
        "wiki_aggregated": {"impressions": 2935973, "clicks": 2325},
        "amp_aggregated": {"impressions": 463225, "clicks": 5878},
    }
)


@pytest.fixture(name="filemanager")
def fixture_filemanager() -> ADMFilemanager:
    """Return a fresh ADMFilemanager instance for test."""
    return ADMFilemanager(gcs_bucket_path=GCS_BUCKET, blob_name=BLOB_NAME)


@pytest.fixture(name="mock_blob")
def fixture_mock_blob(mocker: MockerFixture):
    """Return a mock gcloud.aio.storage Blob."""
    blob = mocker.AsyncMock()
    blob.download = mocker.AsyncMock(return_value=SAMPLE_ENGAGEMENT_JSON.encode())
    return blob


@pytest.fixture(name="mock_bucket")
def fixture_mock_bucket(mocker: MockerFixture, mock_blob):
    """Return a mock gcloud.aio.storage Bucket."""
    bucket = mocker.AsyncMock()
    bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)
    return bucket


def test_get_bucket_lazily_creates_client_and_bucket(
    mocker: MockerFixture,
    filemanager: ADMFilemanager,
    mock_bucket,
) -> None:
    """Test that get_bucket() creates the GCS client and Bucket on first call."""
    mock_storage_cls = mocker.patch("merino.providers.suggest.adm.backends.filemanager.Storage")
    mocker.patch(
        "merino.providers.suggest.adm.backends.filemanager.Bucket", return_value=mock_bucket
    )

    assert filemanager.gcs_client is None
    assert filemanager.bucket is None

    bucket = filemanager.get_bucket()

    mock_storage_cls.assert_called_once()
    assert bucket is mock_bucket
    assert filemanager.bucket is mock_bucket


def test_get_bucket_returns_cached_bucket(
    mocker: MockerFixture,
    filemanager: ADMFilemanager,
    mock_bucket,
) -> None:
    """Test that get_bucket() returns the cached Bucket without recreating the client."""
    filemanager.bucket = mock_bucket
    mock_storage_cls = mocker.patch("merino.providers.suggest.adm.backends.filemanager.Storage")

    bucket = filemanager.get_bucket()

    mock_storage_cls.assert_not_called()
    assert bucket is mock_bucket


@pytest.mark.asyncio
async def test_get_file_success(
    mocker: MockerFixture,
    filemanager: ADMFilemanager,
    mock_bucket,
    mock_blob,
) -> None:
    """Test that get_file() downloads the blob and returns parsed engagement data."""
    mocker.patch("merino.providers.suggest.adm.backends.filemanager.Storage")
    mocker.patch(
        "merino.providers.suggest.adm.backends.filemanager.Bucket", return_value=mock_bucket
    )

    result = await filemanager.get_file()

    mock_bucket.get_blob.assert_called_once_with(BLOB_NAME)
    mock_blob.download.assert_called_once()
    assert result is not None
    assert result.amp["1-800 flowers"]["clicks"] == 10
    assert result.amp_aggregated["impressions"] == 463225
    # wiki_aggregated should not be loaded into EngagementData
    assert not hasattr(result, "wiki_aggregated")


@pytest.mark.asyncio
async def test_get_file_json_decode_error(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    filemanager: ADMFilemanager,
    mock_bucket,
    mock_blob,
) -> None:
    """Test that get_file() returns None and logs an error on invalid JSON."""
    mock_blob.download.return_value = b"not valid json {"
    mocker.patch("merino.providers.suggest.adm.backends.filemanager.Storage")
    mocker.patch(
        "merino.providers.suggest.adm.backends.filemanager.Bucket", return_value=mock_bucket
    )

    result = await filemanager.get_file()

    assert result is None
    assert any("Failed to decode engagement data JSON" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_file_gcs_exception(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    filemanager: ADMFilemanager,
    mock_bucket,
) -> None:
    """Test that get_file() returns None and logs an error when GCS raises an exception."""
    mock_bucket.get_blob.side_effect = Exception("GCS timeout")
    mocker.patch("merino.providers.suggest.adm.backends.filemanager.Storage")
    mocker.patch(
        "merino.providers.suggest.adm.backends.filemanager.Bucket", return_value=mock_bucket
    )

    result = await filemanager.get_file()

    assert result is None
    assert any("GCS timeout" in r.message for r in caplog.records)
