# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the massive filemanager module."""

import pytest
import orjson
from gcloud.aio.storage import Blob

from merino.providers.suggest.finance.backends.massive.filemanager import (
    MassiveFilemanager,
)
from merino.providers.suggest.finance.backends.protocol import (
    FinanceManifest,
    GetManifestResultCode,
)

MOCK_MANIFEST = FinanceManifest(tickers={"AAPL": "https://example.com/aapl.png"})


@pytest.mark.asyncio
async def test_get_file_success(mocker):
    """Test that `get_file()` successfully downloads and deserializes a valid
    FinanceManifest from GCS and returns its updated timestamp.
    """
    mock_data = {"tickers": {"AAPL": "https://example.com/aapl.png"}}
    blob_data = orjson.dumps(mock_data)

    mock_blob = mocker.AsyncMock(spec=Blob)
    mock_blob.download.return_value = blob_data

    mock_bucket = mocker.MagicMock()
    mock_bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)

    filemanager = MassiveFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    result_code, manifest = await filemanager.get_file()

    assert result_code == GetManifestResultCode.SUCCESS
    assert isinstance(manifest, FinanceManifest)
    assert "AAPL" in manifest.tickers


@pytest.mark.asyncio
async def test_get_file_invalid_json(mocker):
    """Test that `get_file` returns FAIL and None when the downloaded blob
    contains invalid JSON.
    """
    mock_blob = mocker.AsyncMock(spec=Blob)
    mock_blob.download.return_value = b"invalid json"

    mock_bucket = mocker.MagicMock()
    mock_bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)

    filemanager = MassiveFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    result_code, manifest = await filemanager.get_file()

    assert result_code == GetManifestResultCode.FAIL
    assert manifest is None


@pytest.mark.asyncio
async def test_get_file_validation_error(mocker):
    """Test that `get_file` returns FAIL and None when the manifest content fails validation."""
    invalid_data = {"tickers": {"AAPL": "not-a-url"}}

    mock_blob = mocker.AsyncMock()
    mock_blob.download.return_value = orjson.dumps(invalid_data)

    mock_bucket = mocker.MagicMock()
    mock_bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)

    filemanager = MassiveFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    result_code, manifest = await filemanager.get_file()

    assert result_code == GetManifestResultCode.FAIL
    assert manifest is None


@pytest.mark.asyncio
async def test_get_bucket_memoization(mocker):
    """Test that get_bucket returns the same bucket instance on multiple calls (memoized)."""
    mock_storage = mocker.patch(
        "merino.providers.suggest.finance.backends.massive.filemanager.Storage"
    )
    mock_bucket_instance = mocker.MagicMock()
    mock_storage.return_value = mocker.MagicMock()
    mocker.patch("gcloud.aio.storage.Bucket", return_value=mock_bucket_instance)

    filemanager = MassiveFilemanager("mock-bucket", "mock-blob")

    bucket1 = await filemanager.get_bucket()
    bucket2 = await filemanager.get_bucket()

    assert bucket1 is bucket2
    assert mock_storage.call_count == 1  # only one Storage instance should be created


@pytest.mark.asyncio
async def test_get_file_uses_get_bucket(mocker):
    """Test that get_file calls get_bucket and fetches the blob."""
    mock_blob = mocker.AsyncMock()
    mock_blob.download.return_value = orjson.dumps(
        {"tickers": {"AAPL": "https://example.com/aapl.png"}}
    )

    mock_bucket = mocker.AsyncMock()
    mock_bucket.get_blob.return_value = mock_blob

    filemanager = MassiveFilemanager("mock-bucket", "mock-blob")
    mocker.patch.object(filemanager, "get_bucket", return_value=mock_bucket)

    result_code, manifest = await filemanager.get_file()

    assert result_code == GetManifestResultCode.SUCCESS
    assert isinstance(manifest, FinanceManifest)
    filemanager.get_bucket.assert_called_once()


@pytest.mark.asyncio
async def test_get_bucket_initializes_client_and_bucket(mocker):
    """Test that get_bucket initializes gcs_client and bucket if unset."""
    # create mock instances
    mock_storage_instance = mocker.MagicMock(name="MockStorageInstance")
    mock_bucket_instance = mocker.MagicMock(name="MockBucketInstance")

    mock_storage_class = mocker.patch(
        "merino.providers.suggest.finance.backends.massive.filemanager.Storage",
        return_value=mock_storage_instance,
    )
    mock_bucket_class = mocker.patch(
        "merino.providers.suggest.finance.backends.massive.filemanager.Bucket",
        return_value=mock_bucket_instance,
    )

    # instantiate filemanager with no initialized clients
    filemanager = MassiveFilemanager("test-bucket", "manifest.json")

    # confirm client and bucket are None before call
    assert filemanager.gcs_client is None
    assert filemanager.bucket is None

    result = await filemanager.get_bucket()

    # check that lazy init worked correctly
    mock_storage_class.assert_called_once_with()
    mock_bucket_class.assert_called_once_with(storage=mock_storage_instance, name="test-bucket")

    assert filemanager.gcs_client is mock_storage_instance
    assert filemanager.bucket is mock_bucket_instance
    assert result is mock_bucket_instance
