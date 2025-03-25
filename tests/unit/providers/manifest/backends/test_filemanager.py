# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the manifest backend filemanager module."""

import orjson
import pytest
import logging
from unittest.mock import AsyncMock
from tests.types import FilterCaplogFixture
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.protocol import GetManifestResultCode, ManifestData


@pytest.mark.asyncio
async def test_get_file_async(
    fixture_filemanager, caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Test that the async get_file method returns manifest data."""
    get_file_result_code, result = await fixture_filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.SUCCESS
    assert isinstance(result, ManifestData)
    assert result.domains
    assert len(result.domains) == 3
    assert result.domains[0].domain == "google"

    # assert correct success log is emitted
    with caplog.at_level(logging.INFO):
        records: list[logging.LogRecord] = filter_caplog(
            caplog.records, "merino.providers.manifest.backends.filemanager"
        )
        for record in records:
            assert record.message.startswith("Successfully loaded remote manifest file")


@pytest.mark.asyncio
async def test_get_file_json_decode_error(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Test that the async get_file method handles JSON decode errors."""
    mock_blob = AsyncMock()
    # returns a non json value
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

    # assert correct error log is emitted
    with caplog.at_level(logging.ERROR):
        records: list[logging.LogRecord] = filter_caplog(
            caplog.records, "merino.providers.manifest.backends.filemanager"
        )
        for record in records:
            assert record.message.startswith("Failed to decode manifest JSON")


@pytest.mark.asyncio
async def test_get_file_validation_error(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Test that the async get_file method handles validation errors for invalid content."""
    mock_blob = AsyncMock()
    # returns invalid field
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

    # assert correct error log is emitted
    with caplog.at_level(logging.ERROR):
        records: list[logging.LogRecord] = filter_caplog(
            caplog.records, "merino.providers.manifest.backends.filemanager"
        )
        for record in records:
            assert record.message.startswith("Invalid manifest content")


@pytest.mark.asyncio
async def test_get_file_exception(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Test that the async get_file method handles unexpected exceptions."""
    mock_bucket = AsyncMock()
    # throws an exception
    mock_bucket.get_blob.side_effect = Exception("Unexpected error")

    mock_storage = AsyncMock()
    mock_storage.bucket.return_value = mock_bucket

    filemanager = ManifestRemoteFilemanager("test-bucket", "test-blob")
    filemanager.gcs_client = mock_storage
    filemanager.bucket = mock_bucket

    get_file_result_code, result = await filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None

    # assert correct error log is emitted
    with caplog.at_level(logging.ERROR):
        records: list[logging.LogRecord] = filter_caplog(
            caplog.records, "merino.providers.manifest.backends.filemanager"
        )
        for record in records:
            assert record.message.startswith("Error fetching remote manifest file")
