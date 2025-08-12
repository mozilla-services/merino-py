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
