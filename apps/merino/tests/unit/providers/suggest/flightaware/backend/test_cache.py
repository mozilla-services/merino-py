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
from merino.providers.suggest.flightaware.backends.errors import (
    FlightawareError,
    FlightawareErrorMessages,
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
@pytest.mark.parametrize(
    "bad_data",
    [
        b"not-json",  # JSONDecodeError
        b"{bad}",  # JSONDecodeError
        b"[]",  # pydantic.ValidationError due to wrong structure
        b"\xff",  # UnicodeDecodeError when decoding UTF-8
    ],
)
async def test_get_flight_raises_flightaware_error_on_parsing_errors(bad_data):
    """Raise FlightawareError (CACHE_DATA_PARSING_ERROR) on bad cached bytes."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = bad_data
    cache = FlightCache(mock_redis)

    with pytest.raises(FlightawareError) as exc:
        await cache.get_flight("UA123")

    expected_msg = FlightawareErrorMessages.CACHE_DATA_PARSING_ERROR.format_message(
        flight_num="UA123"
    )
    assert expected_msg in str(exc.value)


@pytest.mark.asyncio
async def test_get_flight_raises_flightaware_error_on_cache_adapter_error():
    """Raise FlightawareError (CACHE_READ_ERROR) on CacheAdapterError."""
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = CacheAdapterError("boom")

    cache = FlightCache(mock_redis)

    with pytest.raises(FlightawareError) as exc:
        await cache.get_flight("UA123")

    expected_msg = FlightawareErrorMessages.CACHE_READ_ERROR.format_message(flight_num="UA123")
    assert expected_msg in str(exc.value)


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
async def test_set_flight_raises_flightaware_error_on_cache_adapter_error():
    """Raise FlightawareError (CACHE_WRITE_ERROR) when Redis write fails."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = CacheAdapterError("write failed")

    cache = FlightCache(mock_redis)

    with pytest.raises(FlightawareError) as exc:
        await cache.set_flight("UA123", [make_summary()], 600)

    expected_msg = FlightawareErrorMessages.CACHE_WRITE_ERROR.format_message(flight_num="UA123")
    assert expected_msg in str(exc.value)


@pytest.mark.asyncio
async def test_set_flight_raises_flightaware_error_on_serialization_failure(
    monkeypatch,
):
    """Raise FlightawareError (CACHE_DATA_PARSING_ERROR) if json serialization fails."""
    mock_redis = AsyncMock()
    cache = FlightCache(mock_redis)

    # force json.dumps to fail with a TypeError to simulate non-serializable payload
    def boom(_):
        raise TypeError("not serializable")

    monkeypatch.setattr("merino.providers.suggest.flightaware.backends.cache.json.dumps", boom)

    with pytest.raises(FlightawareError) as exc:
        await cache.set_flight("UA123", [make_summary()], 600)

    expected_msg = FlightawareErrorMessages.CACHE_DATA_PARSING_ERROR.format_message(
        flight_num="UA123"
    )
    assert expected_msg in str(exc.value)
