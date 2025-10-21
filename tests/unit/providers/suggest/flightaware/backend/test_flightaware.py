# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the flightaware backend module."""

import datetime
import aiodogstatsd
from pydantic import HttpUrl
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import HTTPStatusError, Request, Response

from merino.providers.suggest.flightaware.backends import utils

from merino.providers.suggest.flightaware.backends.protocol import (
    AirlineDetails,
    AirportDetails,
    FlightScheduleSegment,
    FlightStatus,
    FlightSummary,
    GetFlightNumbersResultCode,
)
from merino.providers.suggest.flightaware.backends.flightaware import FlightAwareBackend
from merino.configs import settings


def make_summary(flight_number: str) -> FlightSummary:
    """Construct a minimal valid FlightSummary."""
    return FlightSummary(
        flight_number=flight_number,
        destination=AirportDetails(code="EWR", city="Newark"),
        origin=AirportDetails(code="SFO", city="San Francisco"),
        departure=FlightScheduleSegment(
            scheduled_time="2025-10-03T16:40:00-04:00",
            estimated_time="2025-10-03T16:40:00-04:00",
        ),
        arrival=FlightScheduleSegment(
            scheduled_time="2025-10-03T18:40:00-04:00",
            estimated_time="2025-10-03T18:40:00-04:00",
        ),
        status="En Route",
        delayed=False,
        airline=AirlineDetails(code=None, name=None, icon=None),
        time_left_minutes=60,
        progress_percent=50,
        url=HttpUrl(f"https://www.flightaware.com/live/flight/{flight_number}"),
    )


@pytest.fixture
def fixed_now():
    """Provide a fixed UTC datetime (2025-09-29T12:00:00Z) for testing."""
    return datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def metrics():
    """Return a mocked metrics client."""
    return MagicMock(spec=aiodogstatsd.Client)


@pytest.fixture
def backend(metrics):
    """Return a FlightAwareBackend with mocked HTTP client and metrics."""
    mock_http_client = AsyncMock()
    backend = FlightAwareBackend(
        api_key=settings.flightaware.api_key,
        http_client=mock_http_client,
        ident_url="flights/{ident}?start={start}&end={end}",
        metrics_client=metrics,
    )
    return backend


@pytest.mark.asyncio
async def test_fetch_flight_details_success(backend, metrics):
    """Ensure fetch_flight_details returns parsed JSON and records metrics on success."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"flights": [{"ident": "UA123"}]}
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    backend.http_client.get.return_value = mock_response

    result = await backend.fetch_flight_details("UA123")

    assert result == {"flights": [{"ident": "UA123"}]}
    backend.http_client.get.assert_called_once()

    metrics.increment.assert_any_call("flightaware.request.summary.get.count")
    metrics.timeit.assert_called_once_with("flightaware.request.summary.get.latency")
    metrics.increment.assert_any_call(
        "flightaware.request.summary.get.status",
        tags={"status_code": 200},
    )


@pytest.mark.asyncio
async def test_fetch_flight_details_http_error_logs_and_returns_none(backend, metrics, caplog):
    """Ensure fetch_flight_details logs a warning and increments error metrics on HTTPStatusError."""
    mock_response = MagicMock()
    request = Request("GET", "http://test")
    response = Response(400, request=request)
    mock_response.raise_for_status.side_effect = HTTPStatusError(
        "Bad Request", request=request, response=response
    )
    mock_response.status_code = 400
    backend.http_client.get.return_value = mock_response

    result = await backend.fetch_flight_details("UA123")

    assert result is None
    assert "Flightware request error for flight details" in caplog.text

    metrics.increment.assert_any_call("flightaware.request.summary.get.count")
    metrics.timeit.assert_called_once_with("flightaware.request.summary.get.latency")
    metrics.increment.assert_any_call(
        "flightaware.request.summary.get.status",
        tags={"status_code": 400},
    )


@pytest.mark.asyncio
async def test_fetch_flight_details_uses_correct_headers(backend, metrics):
    """Verify fetch_flight_details sends the required API key and Accept headers."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {"flights": []}
    mock_response.raise_for_status.return_value = None
    backend.http_client.get.return_value = mock_response

    await backend.fetch_flight_details("UA123")

    _, kwargs = backend.http_client.get.call_args
    headers = kwargs["headers"]
    assert headers["x-apikey"] == settings.flightaware.api_key
    assert headers["Accept"] == "application/json"


def test_get_flight_summaries_returns_empty_list_when_response_is_none(backend):
    """Ensure get_flight_summaries returns empty list if flight_response is None."""
    result = backend.get_flight_summaries(None, "UA123")
    assert result == []


def test_get_flight_summaries_returns_empty_list_when_no_flights(backend):
    """Ensure get_flight_summaries returns empty list if 'flights' is empty."""
    result = backend.get_flight_summaries({"flights": []}, "UA123")
    assert result == []


def test_get_flight_summaries_filters_out_none_summaries(backend):
    """Ensure get_flight_summaries excludes flights where build_flight_summary returns None."""
    good_flight = {
        "ident_iata": "UA123",
        "ident_icao": "UAL123",
        "codeshares_iata": [],
        "codeshares": [],
        "destination": {
            "code_iata": "EWR",
            "city": "Newark",
            "timezone": "America/New_York",
        },
        "origin": {
            "code_iata": "SFO",
            "city": "San Francisco",
            "timezone": "America/Los_Angeles",
        },
        "scheduled_out": "2025-09-29T12:00:00Z",
        "estimated_out": "2025-09-29T12:05:00Z",
        "scheduled_in": "2025-09-29T16:00:00Z",
        "estimated_in": "2025-09-29T16:05:00Z",
        "status": "Scheduled",
        "progress_percent": 0,
    }

    bad_flight = {
        "origin": {"code_iata": "SFO", "city": "San Francisco"},
        "codeshares_iata": [],
        "codeshares": [],
        "scheduled_out": "2025-09-29T12:00:00Z",
        "estimated_out": "2025-09-29T12:05:00Z",
        "status": "Scheduled",
        "progress_percent": 0,
    }
    flights = [good_flight, bad_flight]
    result = backend.get_flight_summaries({"flights": flights}, "UA123")

    assert len(result) == 1
    summary = result[0]
    assert isinstance(summary, FlightSummary)
    assert summary.flight_number == "UA123"
    assert summary.origin.city == "San Francisco"
    assert summary.destination.code == "EWR"


def test_get_flight_summaries_returns_multiple_valid_summaries(fixed_now, backend):
    """Ensure get_flight_summaries returns multiple summaries when build_flight_summary succeeds."""
    flights = [
        {
            "ident_iata": "UA111",
            "ident_icao": "UAL111",
            "codeshares_iata": [],
            "codeshares": [],
            "destination": {
                "code_iata": "EWR",
                "city": "Newark",
                "timezone": "America/New_York",
            },
            "origin": {
                "code_iata": "SFO",
                "city": "San Francisco",
                "timezone": "America/Los_Angeles",
            },
            "scheduled_out": "2025-09-29T10:00:00Z",
            "estimated_out": "2025-09-29T10:05:00Z",
            "actual_out": "2025-09-29T10:05:00Z",
            "actual_in": "2025-09-29T11:25:00Z",
            "scheduled_in": "2025-09-29T10:00:00Z",
            "estimated_in": "2025-09-29T10:05:00Z",
            "status": "Arrived / At Gate",
            "progress_percent": 0,
        },
        {
            "ident_iata": "UA111",
            "ident_icao": "UAL111",
            "codeshares_iata": [],
            "codeshares": [],
            "destination": {
                "code_iata": "EWR",
                "city": "Newark",
                "timezone": "America/New_York",
            },
            "origin": {
                "code_iata": "SFO",
                "city": "San Francisco",
                "timezone": "America/Los_Angeles",
            },
            "scheduled_out": "2025-09-29T14:00:00Z",
            "estimated_out": "2025-09-29T14:16:00Z",
            "scheduled_in": "2025-09-29T18:00:00Z",
            "estimated_in": "2025-09-29T18:20:00Z",
            "status": "Scheduled / Not departed",
            "departure_delay": 960,
            "progress_percent": 0,
        },
    ]

    with patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        results = backend.get_flight_summaries({"flights": flights}, "UA111")

    assert len(results) == 2
    assert all(isinstance(r, FlightSummary) for r in results)
    assert results[0].status == FlightStatus.ARRIVED
    assert results[1].status == FlightStatus.DELAYED


@pytest.mark.asyncio
async def test_fetch_flight_numbers_success(backend):
    """Ensure fetch_flight_numbers returns SUCCESS and expected list."""
    mock_filemanager = AsyncMock()
    mock_filemanager.get_file.return_value = (
        GetFlightNumbersResultCode.SUCCESS,
        ["UA123", "AA100"],
    )
    backend.filemanager = mock_filemanager

    result_code, data = await backend.fetch_flight_numbers()

    assert result_code == GetFlightNumbersResultCode.SUCCESS
    assert data == ["UA123", "AA100"]
    mock_filemanager.get_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_flight_numbers_fail(backend):
    """Ensure fetch_flight_numbers returns FAIL when filemanager fails."""
    mock_filemanager = AsyncMock()
    mock_filemanager.get_file.return_value = (GetFlightNumbersResultCode.FAIL, None)
    backend.filemanager = mock_filemanager

    result_code, data = await backend.fetch_flight_numbers()

    assert result_code == GetFlightNumbersResultCode.FAIL
    assert data is None
    mock_filemanager.get_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_flight_numbers_exception(backend, caplog):
    """Ensure fetch_flight_numbers logs error and returns FAIL on exception."""
    mock_filemanager = AsyncMock()
    mock_filemanager.get_file.side_effect = Exception("GCS failure")
    backend.filemanager = mock_filemanager

    with caplog.at_level("WARNING"):
        result_code, result = await backend.fetch_flight_numbers()

    assert result_code == GetFlightNumbersResultCode.FAIL
    assert result is None
    assert "Failed to fetch flight numbers from GCS" in caplog.text
