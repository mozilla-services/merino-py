# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the manifest backend filemanager module."""

import orjson
import pytest
from unittest.mock import AsyncMock
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.protocol import GetManifestResultCode, ManifestData


# TODO ADD the new fixture here
@pytest.mark.asyncio
async def test_get_file_async(fixture_filemanager):
    """Test that the async get_file method returns manifest data."""
    get_file_result_code, result = await fixture_filemanager.get_file()

    # Assertions
    assert get_file_result_code is GetManifestResultCode.SUCCESS
    assert isinstance(result, ManifestData)
    assert result.domains
    assert len(result.domains) == 3
    assert result.domains[0].domain == "google"


@pytest.mark.asyncio
async def test_get_file_json_decode_error():
    """Test that the async get_file method handles JSON decode errors."""
    mock_blob = AsyncMock()
    mock_blob.download.return_value = b"invalid json"

    mock_bucket = AsyncMock()
    mock_bucket.get_blob.return_value = mock_blob

    mock_storage = AsyncMock()
    mock_storage.bucket.return_value = mock_bucket

    filemanager = ManifestRemoteFilemanager("test-bucket", "test-blob")
    filemanager.gcs_client = mock_storage
    filemanager.bucket = mock_bucket

    get_file_result_code, result = await filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None


@pytest.mark.asyncio
async def test_get_file_validation_error():
    """Test that the async get_file method handles validation errors."""
    mock_blob = AsyncMock()
    mock_blob.download.return_value = orjson.dumps({"invalid_field": "data"})

    mock_bucket = AsyncMock()
    mock_bucket.get_blob.return_value = mock_blob

    mock_storage = AsyncMock()
    mock_storage.bucket.return_value = mock_bucket

    filemanager = ManifestRemoteFilemanager("test-bucket", "test-blob")
    filemanager.gcs_client = mock_storage
    filemanager.bucket = mock_bucket

    get_file_result_code, result = await filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None


@pytest.mark.asyncio
async def test_get_file_exception():
    """Test that the async get_file method handles unexpected exceptions."""
    mock_bucket = AsyncMock()
    mock_bucket.get_blob.side_effect = Exception("Unexpected error")

    mock_storage = AsyncMock()
    mock_storage.bucket.return_value = mock_bucket

    filemanager = ManifestRemoteFilemanager("test-bucket", "test-blob")
    filemanager.gcs_client = mock_storage
    filemanager.bucket = mock_bucket

    get_file_result_code, result = await filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None
