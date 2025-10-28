# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Flightaware cache module."""

import json
import datetime
import pytest
from unittest.mock import AsyncMock

from merino.providers.suggest.flightaware.backends.cache import (
    FlightCache,
    CachedFlightData,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    FlightSummary,
    AirportDetails,
    AirlineDetails,
    FlightScheduleSegment,
)
from merino.exceptions import CacheAdapterError


def make_summary() -> FlightSummary:
    """Return a sample FlightSummary."""
    return FlightSummary(
        flight_number="UA123",
        destination=AirportDetails(code="EWR", city="Newark"),
        origin=AirportDetails(code="SFO", city="San Francisco"),
        departure=FlightScheduleSegment(
            scheduled_time="2025-09-29T12:00:00Z",
            estimated_time="2025-09-29T12:05:00Z",
        ),
        arrival=FlightScheduleSegment(
            scheduled_time="2025-09-29T16:00:00Z",
            estimated_time="2025-09-29T16:05:00Z",
        ),
        status="Scheduled",
        delayed=False,
        airline=AirlineDetails(code="UA", name="United Airlines", icon=None),
        progress_percent=0,
        time_left_minutes=None,
        url="https://www.flightaware.com/live/flight/UA123",
    )


@pytest.mark.asyncio
async def test_get_flight_returns_valid_cached_data(caplog):
    """Ensure get_flight parses valid JSON into CachedFlightData."""
    mock_redis = AsyncMock()
    payload = {"summaries": [make_summary().model_dump(mode="json")]}
    mock_redis.get.return_value = json.dumps(payload).encode("utf-8")

    cache = FlightCache(mock_redis)
    result = await cache.get_flight("UA123")

    assert isinstance(result, CachedFlightData)
    assert result.summaries[0].flight_number == "UA123"
    mock_redis.get.assert_awaited_once_with("flight_status:UA123")
    assert "Error" not in caplog.text


@pytest.mark.asyncio
async def test_get_flight_returns_none_if_no_data():
    """Return None when redis.get returns None or empty."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    cache = FlightCache(mock_redis)
    result = await cache.get_flight("UA123")

    assert result is None
    mock_redis.get.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_data", [b"not-json", b"{bad}", b"[]"])
async def test_get_flight_returns_none_on_invalid_json(bad_data):
    """Return None if redis returns invalid JSON or wrong structure."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = bad_data

    cache = FlightCache(mock_redis)
    result = await cache.get_flight("UA123")

    assert result is None


@pytest.mark.asyncio
async def test_get_flight_logs_and_returns_none_on_cache_adapter_error(caplog):
    """Return None and log warning if CacheAdapterError is raised."""
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = CacheAdapterError("boom")

    cache = FlightCache(mock_redis)
    result = await cache.get_flight("UA123")

    assert result is None
    assert "Error while getting flight summaries" in caplog.text


@pytest.mark.asyncio
async def test_set_flight_writes_correct_payload():
    """Verify set_flight serializes summaries and sets Redis with proper TTL."""
    mock_redis = AsyncMock()
    cache = FlightCache(mock_redis)

    summaries = [make_summary()]
    ttl_seconds = 600

    await cache.set_flight("UA123", summaries, ttl_seconds)

    mock_redis.set.assert_awaited_once()
    call_args = mock_redis.set.await_args
    key, value = call_args.args
    ttl = call_args.kwargs["ttl"]

    assert key == "flight_status:UA123"
    assert isinstance(ttl, datetime.timedelta)
    assert ttl.total_seconds() == ttl_seconds

    decoded = json.loads(value.decode("utf-8"))
    assert "summaries" in decoded
    assert decoded["summaries"][0]["flight_number"] == "UA123"


@pytest.mark.asyncio
async def test_set_flight_logs_warning_on_cache_adapter_error(caplog):
    """If redis.set raises CacheAdapterError, warning should be logged."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = CacheAdapterError("write failed")

    cache = FlightCache(mock_redis)
    await cache.set_flight("UA123", [make_summary()], 600)

    assert "Error while setting flight summaries" in caplog.text
