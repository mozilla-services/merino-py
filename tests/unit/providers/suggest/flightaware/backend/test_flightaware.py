# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the flightaware backend module."""

from pydantic import HttpUrl
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import HTTPStatusError, Request, Response

import merino.providers.suggest.flightaware.backends.flightaware as flightaware

from merino.providers.suggest.flightaware.backends.protocol import (
    AirportDetails,
    FlightScheduleSegment,
    FlightSummary,
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
            scheduled_time="2025-09-29T12:00:00Z", estimated_time="2025-09-29T12:05:00Z"
        ),
        arrival=FlightScheduleSegment(
            scheduled_time="2025-09-29T16:00:00Z", estimated_time="2025-09-29T16:05:00Z"
        ),
        status="En Route",
        progress_percent=50,
        url=HttpUrl(f"https://www.flightaware.com/live/flight/{flight_number}"),
    )


@pytest.mark.asyncio
async def test_fetch_flight_details_success():
    """Ensure fetch_flight_details returns parsed JSON when the API responds successfully."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"flights": [{"ident": "UA123"}]}
    mock_response.raise_for_status.return_value = None
    mock_http_client.get.return_value = mock_response

    backend = flightaware.FlightAwareBackend(
        api_key=settings.flightaware.api_key,
        http_client=mock_http_client,
        ident_url="flights/{ident}?start={start}&end={end}",
    )

    result = await backend.fetch_flight_details("UA123")

    assert result == {"flights": [{"ident": "UA123"}]}
    mock_http_client.get.assert_called_once()

    called_url = mock_http_client.get.call_args[0][0]
    assert called_url.startswith("flights/UA123?start=")


@pytest.mark.asyncio
async def test_fetch_flight_details_http_error_logs_and_returns_none(caplog):
    """Ensure fetch_flight_details logs a warning and returns None when HTTPStatusError is raised."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    request = Request("GET", "http://test")
    mock_response.raise_for_status.side_effect = HTTPStatusError(
        "Bad Request",
        request=request,
        response=Response(400, request=request),
    )
    mock_http_client.get.return_value = mock_response

    backend = flightaware.FlightAwareBackend(
        api_key=settings.flightaware.api_key,
        http_client=mock_http_client,
        ident_url="flights/{ident}?start={start}&end={end}",
    )

    result = await backend.fetch_flight_details("UA123")

    assert result is None
    assert "Flightware request error for flight details" in caplog.text


@pytest.mark.asyncio
async def test_fetch_flight_details_uses_correct_headers():
    """Verify fetch_flight_details sends the required API key and Accept headers."""
    mock_http_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {"flights": []}
    mock_response.raise_for_status.return_value = None
    mock_http_client.get.return_value = mock_response

    backend = flightaware.FlightAwareBackend(
        api_key=settings.flightaware.api_key,
        http_client=mock_http_client,
        ident_url="flights/{ident}?start={start}&end={end}",
    )

    await backend.fetch_flight_details("UA123")

    _, kwargs = mock_http_client.get.call_args
    headers = kwargs["headers"]
    assert headers["x-apikey"] == settings.flightaware.api_key
    assert headers["Accept"] == "application/json"


def test_get_flight_summaries_returns_empty_list_when_response_is_none():
    """Ensure get_flight_summaries returns empty list if flight_response is None."""
    backend = FlightAwareBackend(api_key="k", http_client=MagicMock(), ident_url="url")
    result = backend.get_flight_summaries(None, "UA123")
    assert result == []


def test_get_flight_summaries_returns_empty_list_when_no_flights():
    """Ensure get_flight_summaries returns empty list if 'flights' is empty."""
    backend = FlightAwareBackend(api_key="k", http_client=MagicMock(), ident_url="url")
    result = backend.get_flight_summaries({"flights": []}, "UA123")
    assert result == []


def test_get_flight_summaries_filters_out_none_summaries():
    """Ensure get_flight_summaries excludes flights where build_flight_summary returns None."""
    backend = FlightAwareBackend(api_key="k", http_client=MagicMock(), ident_url="url")
    flights = [{"id": "good"}, {"id": "bad"}]

    summary = make_summary("UA123")

    with patch(
        "merino.providers.suggest.flightaware.backends.flightaware.build_flight_summary"
    ) as mock_build:
        mock_build.side_effect = [
            summary,
            None,
        ]
        result = backend.get_flight_summaries({"flights": flights}, "UA123")

    assert len(result) == 1
    assert isinstance(result[0], FlightSummary)
    assert result[0].flight_number == "UA123"
    assert result[0].origin.city == "San Francisco"
    assert result[0].destination.code == "EWR"


def test_get_flight_summaries_returns_multiple_valid_summaries():
    """Ensure get_flight_summaries returns multiple summaries when build_flight_summary succeeds."""
    backend = FlightAwareBackend(api_key="k", http_client=MagicMock(), ident_url="url")
    flights = [{"id": "f1"}, {"id": "f2"}]

    summary1 = make_summary("UA111")
    summary2 = make_summary("UA222")

    with patch(
        "merino.providers.suggest.flightaware.backends.flightaware.build_flight_summary"
    ) as mock_build:
        mock_build.side_effect = [summary1, summary2]
        result = backend.get_flight_summaries({"flights": flights}, "UA123")

    assert len(result) == 2
    assert all(isinstance(s, FlightSummary) for s in result)
    assert {s.flight_number for s in result} == {"UA111", "UA222"}
