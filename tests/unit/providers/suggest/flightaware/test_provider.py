# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the flightaware provider module."""

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.middleware.geolocation import Location
from merino.providers.suggest.flightaware.provider import Provider
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.custom_details import CustomDetails, FlightAwareDetails
from merino.providers.suggest.flightaware.backends.protocol import (
    AirlineDetails,
    FlightSummary,
    GetFlightNumbersResultCode,
)


@pytest.fixture
def backend_mock():
    """Return mock flight aware backend"""
    backend = MagicMock()
    backend.fetch_flight_details = AsyncMock()
    backend.get_flight_summaries = MagicMock()
    return backend


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="CA",
        regions=["ON"],
        city="Toronto",
        dma=613,
        postal_code="M5G2B6",
    )


@pytest.fixture
def provider(backend_mock):
    """Return a mock provider"""
    return Provider(
        backend=backend_mock,
        name="flightaware",
        metrics_client=MagicMock(spec=aiodogstatsd.Client),
        query_timeout_sec=1.0,
        score=0.8,
        resync_interval_sec=60,
        cron_interval_sec=60,
    )


def test_validate_rejects_missing_query(provider, geolocation):
    """Validate should raise if query is missing."""
    req = SuggestionRequest(query="", geolocation=geolocation)
    with pytest.raises(HTTPException) as exc:
        provider.validate(req)
    assert exc.value.status_code == 400
    assert "Invalid query parameters" in exc.value.detail


def test_validate_accepts_valid_query(provider, geolocation):
    """Validate should pass if query is present."""
    req = SuggestionRequest(query="UA123", geolocation=geolocation)
    provider.validate(req)


def test_normalize_query_strips_and_uppercases(provider):
    """Normalize_query should strip spaces and uppercase."""
    assert provider.normalize_query(" ua123 ") == "UA123"


@pytest.mark.asyncio
async def test_query_returns_empty_if_query_does_not_match_pattern(provider, geolocation):
    """Query should return empty list if query doesn't match flight number regex."""
    request = SuggestionRequest(query="notaflight", geolocation=geolocation)
    results = await provider.query(request)
    assert results == []


@pytest.mark.asyncio
async def test_query_returns_empty_if_not_in_flight_numbers(provider, geolocation):
    """Query should return empty list if query matches pattern but not present in flight_numbers cache."""
    provider.flight_numbers = {"UA123", "AA100"}  # known cached flights

    request = SuggestionRequest(query="LH9999", geolocation=geolocation)
    results = await provider.query(request)

    assert results == []


@pytest.mark.asyncio
async def test_query_fetches_and_builds_suggestion_from_cached_numbers(
    provider, backend_mock, geolocation
):
    """Query should call backend and return a built suggestion if query is valid and present in flight_numbers cache."""
    provider.flight_numbers = {"UA3711", "AA100", "AC701"}

    request = SuggestionRequest(query="UA3711", geolocation=geolocation)
    backend_mock.fetch_flight_details.return_value = {"flights": [{"ident": "UA3711"}]}

    fake_summary = FlightSummary(
        flight_number="UA3711",
        destination={"code": "EWR", "city": "Newark"},
        origin={"code": "SFO", "city": "San Francisco"},
        departure={
            "scheduled_time": "2025-09-29T12:00:00Z",
            "estimated_time": "2025-09-29T12:05:00Z",
        },
        arrival={
            "scheduled_time": "2025-09-29T16:00:00Z",
            "estimated_time": "2025-09-29T16:05:00Z",
        },
        status="En Route",
        progress_percent=50,
        airline=AirlineDetails(code=None, name=None, icon=None),
        delayed=False,
        url="https://www.flightaware.com/live/flight/UA3711",
    )
    backend_mock.get_flight_summaries.return_value = [fake_summary]

    results = await provider.query(request)

    assert len(results) == 1
    suggestion = results[0]
    assert isinstance(suggestion, BaseSuggestion)
    assert suggestion.title == "Flight Suggestion"
    assert suggestion.provider == "flightaware"
    assert suggestion.custom_details.flightaware.values[0].flight_number == "UA3711"


@pytest.mark.asyncio
async def test_query_handles_backend_exception(provider, backend_mock, caplog, geolocation):
    """Query should catch exceptions and return empty list if backend fails."""
    provider.flight_numbers = {"UA3711"}
    request = SuggestionRequest(query="UA3711", geolocation=geolocation)
    backend_mock.fetch_flight_details.side_effect = Exception("boom")

    with caplog.at_level("WARNING"):
        results = await provider.query(request)

    assert results == []
    assert "Exception occurred for FlightAware provider" in caplog.text


def test_build_suggestion_creates_expected_object(provider):
    """Build_suggestion should wrap flight summaries into BaseSuggestion with FlightAwareDetails."""
    summary = FlightSummary(
        flight_number="AA100",
        destination={"code": "JFK", "city": "New York"},
        origin={"code": "LAX", "city": "Los Angeles"},
        departure={
            "scheduled_time": "2025-09-29T12:00:00Z",
            "estimated_time": "2025-09-29T12:05:00Z",
        },
        arrival={
            "scheduled_time": "2025-09-29T16:00:00Z",
            "estimated_time": "2025-09-29T16:05:00Z",
        },
        status="Scheduled",
        progress_percent=0,
        airline=AirlineDetails(code=None, name=None, icon=None),
        delayed=False,
        time_left_minutes=None,
        url="https://www.flightaware.com/live/flight/AA100",
    )
    suggestion = provider.build_suggestion([summary])

    assert isinstance(suggestion, BaseSuggestion)
    assert suggestion.title == "Flight Suggestion"
    assert suggestion.url == HttpUrl("https://merino.services.mozilla.com/")
    assert isinstance(suggestion.custom_details, CustomDetails)
    assert isinstance(suggestion.custom_details.flightaware, FlightAwareDetails)
    assert suggestion.custom_details.flightaware.values[0].flight_number == "AA100"


@pytest.mark.asyncio
async def test_fetch_data_success_sets_flight_numbers_and_logs(provider, caplog):
    """_fetch_data should set flight_numbers and log success when backend returns SUCCESS."""
    mock_backend = AsyncMock()
    mock_backend.fetch_flight_numbers.return_value = (
        GetFlightNumbersResultCode.SUCCESS,
        ["UA123", "AA100"],
    )
    provider.backend = mock_backend

    with caplog.at_level(logging.INFO):
        await provider._fetch_data()

    assert provider.flight_numbers == {"UA123", "AA100"}
    assert "Successfully fetched and set flight numbers from backend" in caplog.text
    assert provider.data_fetched_event.is_set()


@pytest.mark.asyncio
async def test_fetch_data_fail_logs_error_and_does_not_set_numbers(provider, caplog):
    """_fetch_data should log error and not set flight_numbers when backend returns FAIL."""
    mock_backend = AsyncMock()
    mock_backend.fetch_flight_numbers.return_value = (
        GetFlightNumbersResultCode.FAIL,
        None,
    )
    provider.backend = mock_backend
    provider.flight_numbers = set()

    with caplog.at_level(logging.ERROR):
        await provider._fetch_data()

    assert provider.flight_numbers == set()
    assert "Failed to fetch data from flightaware backend" in caplog.text
    assert provider.data_fetched_event.is_set()


@pytest.mark.asyncio
async def test_fetch_data_backend_exception_logs_error(provider, caplog):
    """_fetch_data should handle exceptions raised by backend.fetch_flight_numbers."""
    mock_backend = AsyncMock()
    mock_backend.fetch_flight_numbers.side_effect = Exception("Network error")
    provider.backend = mock_backend

    with caplog.at_level(logging.ERROR):
        await provider._fetch_data()

    assert "Failed to fetch data from flightaware backend" in caplog.text
    assert provider.data_fetched_event.is_set()


def test_should_fetch_returns_true_when_interval_exceeded(provider):
    """_should_fetch should return True when enough time has passed since last fetch."""
    with patch("merino.providers.suggest.flightaware.provider.time.time", return_value=2000):
        provider.last_fetch_at = 1000
        provider.resync_interval_sec = 500
        assert provider._should_fetch() is True


def test_should_fetch_returns_false_when_interval_not_exceeded(provider):
    """_should_fetch should return False when interval has not elapsed."""
    with patch("merino.providers.suggest.flightaware.provider.time.time", return_value=2000):
        provider.last_fetch_at = 1700
        provider.resync_interval_sec = 500
        assert provider._should_fetch() is False
