# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the polygon filemanager module."""

import pytest
import orjson
from gcloud.aio.storage import Blob

from merino.providers.suggest.finance.backends.polygon.filemanager import PolygonFilemanager
from merino.providers.suggest.finance.backends.protocol import (
    FinanceManifest,
    GetManifestResultCode,
)

MOCK_MANIFEST = manifest = FinanceManifest(tickers={"AAPL": "https://example.com/aapl.png"})


@pytest.mark.asyncio
async def test_get_file_success(mocker):
    """Test that `get_file()` successfully downloads and deserializes a valid
    FinanceManifest from GCS.
    """
    mock_data = {"tickers": {"AAPL": "https://example.com/aapl.png"}}

    blob_data = orjson.dumps(mock_data)

    mock_blob = mocker.AsyncMock(spec=Blob)
    mock_blob.download.return_value = blob_data

    mock_bucket = mocker.MagicMock()
    mock_bucket.get_blob = mocker.AsyncMock(return_value=mock_blob)

    filemanager = PolygonFilemanager("mock-bucket", "mock-blob")
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

    filemanager = PolygonFilemanager("mock-bucket", "mock-blob")
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

    filemanager = PolygonFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    result_code, manifest = await filemanager.get_file()

    assert result_code == GetManifestResultCode.FAIL
    assert manifest is None


@pytest.mark.asyncio
async def test_upload_file_success(mocker):
    """Test that `upload_file` successfully serializes a valid FinanceManifest
    and uploads it to GCS without errors.
    """
    mock_blob = mocker.AsyncMock(spec=Blob)
    mock_blob.upload = mocker.AsyncMock(return_value=None)

    mocker.patch(
        "merino.providers.suggest.finance.backends.polygon.filemanager.Blob",
        return_value=mock_blob,
    )

    mock_bucket = mocker.MagicMock()
    filemanager = PolygonFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    manifest = MOCK_MANIFEST

    result = await filemanager.upload_file(manifest)

    assert result is True
    mock_blob.upload.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_raises_exception(mocker):
    """Test that `upload_file` handles exceptions during the upload process
    and returns False if GCS blob upload fails.
    """
    mock_blob = mocker.AsyncMock(spec=Blob)
    mock_blob.upload.side_effect = RuntimeError("upload failed")

    mocker.patch(
        "merino.providers.suggest.finance.backends.polygon.filemanager.Blob",
        return_value=mock_blob,
    )

    mock_bucket = mocker.MagicMock()
    filemanager = PolygonFilemanager("mock-bucket", "mock-blob")
    filemanager.bucket = mock_bucket

    manifest = MOCK_MANIFEST

    result = await filemanager.upload_file(manifest)

    assert result is False
