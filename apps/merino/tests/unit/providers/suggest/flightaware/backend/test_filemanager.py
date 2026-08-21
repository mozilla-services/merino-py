# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Flightaware filemanager module."""

import orjson
import pytest
import logging
from unittest.mock import AsyncMock
from tests.types import FilterCaplogFixture

from merino.providers.suggest.flightaware.backends.filemanager import (
    FlightawareFilemanager,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    GetFlightNumbersResultCode,
)


@pytest.mark.asyncio
async def test_get_file_success(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Ensure get_file successfully parses valid flight number data."""
    mock_blob = AsyncMock()
    mock_blob.download.return_value = orjson.dumps(["UA123", "AA100", "AC701"])

    mock_bucket = AsyncMock()
    mock_bucket.get_blob.return_value = mock_blob

    filemanager = FlightawareFilemanager("test-bucket", "test-blob")
    filemanager.bucket = mock_bucket

    with caplog.at_level(logging.INFO):
        result_code, result = await filemanager.get_file()

    assert result_code is GetFlightNumbersResultCode.SUCCESS
    assert isinstance(result, list)
    assert result == ["UA123", "AA100", "AC701"]

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.flightaware.backends.filemanager"
    )
    assert any("Successfully loaded" in r.message for r in records)


@pytest.mark.asyncio
async def test_get_file_json_decode_error(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Ensure get_file gracefully handles JSON decode errors."""
    mock_blob = AsyncMock()
    mock_blob.download.return_value = b"not valid json"

    mock_bucket = AsyncMock()
    mock_bucket.get_blob.return_value = mock_blob

    filemanager = FlightawareFilemanager("test-bucket", "test-blob")
    filemanager.bucket = mock_bucket

    result_code, result = await filemanager.get_file()

    assert result_code is GetFlightNumbersResultCode.FAIL
    assert result is None

    with caplog.at_level(logging.ERROR):
        records = filter_caplog(
            caplog.records, "merino.providers.suggest.flightaware.backends.filemanager"
        )
        assert any("Failed to decode flight numbers JSON" in r.message for r in records)


@pytest.mark.asyncio
async def test_get_file_exception(
    caplog: pytest.LogCaptureFixture, filter_caplog: FilterCaplogFixture
):
    """Ensure get_file handles unexpected exceptions gracefully."""
    mock_bucket = AsyncMock()
    mock_bucket.get_blob.side_effect = Exception("Unexpected error")

    filemanager = FlightawareFilemanager("test-bucket", "test-blob")
    filemanager.bucket = mock_bucket

    result_code, result = await filemanager.get_file()

    assert result_code is GetFlightNumbersResultCode.FAIL
    assert result is None

    with caplog.at_level(logging.ERROR):
        records = filter_caplog(
            caplog.records, "merino.providers.suggest.flightaware.backends.filemanager"
        )
        assert any("Error fetching flight numbers file" in r.message for r in records)
