# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for fetch_schedules.py module."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

import merino.jobs.flightaware.fetch_schedules as fetch_schedules


def test_process_flight_numbers_adds_valid_and_skips_none(caplog):
    """Verify process_flight_numbers adds valid IATA codes and ignores None values."""
    caplog.set_level("INFO")
    flights = [{"ident_iata": "AA123"}, {"ident_iata": None}, {}]
    result = set()

    fetch_schedules.process_flight_numbers(result, flights)

    assert "AA123" in result
    assert len(result) == 1
    assert "Unique flight numbers" in caplog.text


@pytest.mark.asyncio
async def test_store_flight_numbers_dispatch(caplog):
    """Ensure store_flight_numbers dispatches correctly to Redis, GCS, or logs unknown backend."""
    called = {}

    async def fake_redis(numbers):
        called["redis"] = True

    async def fake_gcs(numbers):
        called["gcs"] = True

    with (
        patch.object(fetch_schedules, "store_flight_numbers_in_redis", side_effect=fake_redis),
        patch.object(fetch_schedules, "store_flight_numbers_in_gcs", side_effect=fake_gcs),
    ):
        with patch.object(fetch_schedules, "STORAGE", "redis"):
            await fetch_schedules.store_flight_numbers({"AA123"})
            assert "redis" in called

        with patch.object(fetch_schedules, "STORAGE", "gcs"):
            await fetch_schedules.store_flight_numbers({"AA123"})
            assert "gcs" in called

        with patch.object(fetch_schedules, "STORAGE", "bogus"):
            await fetch_schedules.store_flight_numbers({"AA123"})
            assert "Unknown storage backend" in caplog.text


@pytest.mark.asyncio
async def test_store_flight_numbers_in_redis_chunks():
    """Confirm store_flight_numbers_in_redis splits inserts into chunks and calls sadd multiple times."""
    fake_cache = AsyncMock()
    fake_cache.sadd.side_effect = [10, 5]
    fake_cache.scard.return_value = 15

    with patch.object(fetch_schedules, "cache", fake_cache):
        numbers = {f"FL{i}" for i in range(fetch_schedules.CHUNK_SIZE + 100)}
        await fetch_schedules.store_flight_numbers_in_redis(numbers)

        assert fake_cache.sadd.call_count == 2
        fake_cache.scard.assert_awaited()


@pytest.mark.asyncio
async def test_store_flight_numbers_in_gcs_first_upload():
    """Test that store_flight_numbers_in_gcs uploads all numbers when no blob exists."""
    mock_uploader = MagicMock()
    mock_uploader.get_most_recent_file.return_value = None

    with patch.object(fetch_schedules, "GcsUploader", return_value=mock_uploader):
        await fetch_schedules.store_flight_numbers_in_gcs({"AA123"})

    uploaded = json.loads(mock_uploader.upload_content.call_args[1]["content"])
    assert uploaded == ["AA123"]


@pytest.mark.asyncio
async def test_store_flight_numbers_in_gcs_merges_existing():
    """Check that store_flight_numbers_in_gcs merges new numbers with existing blob and dedupes."""
    mock_blob = MagicMock()
    mock_blob.download_as_text.return_value = json.dumps(["AA123"])

    mock_uploader = MagicMock()
    mock_uploader.get_most_recent_file.return_value = mock_blob

    with patch.object(fetch_schedules, "GcsUploader", return_value=mock_uploader):
        await fetch_schedules.store_flight_numbers_in_gcs({"AA123", "UA456"})

    uploaded = json.loads(mock_uploader.upload_content.call_args[1]["content"])
    assert sorted(uploaded) == ["AA123", "UA456"]


def test_fetch_schedules_handles_links_null(caplog):
    """Ensure fetch_schedules handles a response with 'links': null without crashing."""
    caplog.set_level("INFO")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "scheduled": [{"ident_iata": "AA123"}],
        "links": None,
    }
    mock_response.raise_for_status.return_value = None

    with patch.object(fetch_schedules, "_get_with_retry", return_value=mock_response):
        flights, calls = fetch_schedules.fetch_schedules(mock_client)

    assert flights == {"AA123"}
    assert calls == 1
    assert "Page 1: 1 flights" in caplog.text
