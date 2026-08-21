# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with a flight provider."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pydantic import HttpUrl, TypeAdapter
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.flightaware.provider import Provider as FlightProvider
from merino.providers.suggest.flightaware.backends.errors import (
    FlightawareError,
    FlightawareErrorMessages,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    AirlineDetails,
    FlightBackendProtocol,
    FlightSummary,
    FlightScheduleSegment,
    AirportDetails,
)


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a FlightBackendProtocol mock object for test."""
    backend = mocker.AsyncMock(spec=FlightBackendProtocol)
    backend.shutdown = mocker.AsyncMock()
    return backend


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any, statsd_mock: Any) -> dict[str, FlightProvider]:
    """Define the flight provider used by the suggest endpoint."""
    provider = FlightProvider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        score=0.8,
        name="flightaware",
        query_timeout_sec=0.2,
        enabled_by_default=True,
        resync_interval_sec=60,
        cron_interval_sec=60,
    )
    provider.flight_numbers = {"UA123"}
    return {"flightaware": provider}


@pytest.fixture(name="flight_summary")
def fixture_flight_summary() -> list[FlightSummary]:
    """Return a valid flight summary for UA123."""
    return [
        FlightSummary(
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
            url=HttpUrl("https://www.flightaware.com/live/flight/UA123"),
        )
    ]


def test_suggest_with_flight_summary(
    client: TestClient,
    backend_mock: Any,
    flight_summary: list[FlightSummary],
) -> None:
    """Test that the suggest endpoint returns a flight suggestion when the backend supplies data."""
    backend_mock.fetch_flight_details.return_value = flight_summary

    response = client.get("/api/v1/suggest?q=UA123&providers=flightaware")

    assert response.status_code == 200
    body = response.json()

    suggestions = TypeAdapter(list[BaseSuggestion]).validate_python(body["suggestions"])
    assert len(suggestions) == 1

    assert (
        body["suggestions"][0]["custom_details"]["flightaware"]["values"][0]["flight_number"]
        == "UA123"
    )


def test_circuit_breaker_with_backend_error_flight(
    client: TestClient,
    backend_mock: Any,
    mocker: MockerFixture,
    flight_summary: list[FlightSummary],
) -> None:
    """Verify that the flight provider behaves as expected when its circuit breaker is triggered."""
    # make backend fail with an expected breaker exception type
    backend_mock.fetch_flight_details.side_effect = FlightawareError(
        FlightawareErrorMessages.CACHE_READ_ERROR, flight_num="UA123"
    )

    with freeze_time("2025-04-11") as freezer:
        # trip the breaker by hitting the failing endpoint `threshold`` times
        for _ in range(settings.providers.flightaware.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?providers=flightaware&q=UA123")

        # after open, subsequent calls should be short-circuited and not touch the backend
        spy = mocker.spy(backend_mock, "fetch_flight_details")
        for _ in range(settings.providers.flightaware.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?providers=flightaware&q=UA123")
        spy.assert_not_called()

        # advance time past recovery timeout to allow half-open
        freezer.tick(settings.providers.flightaware.circuit_breaker_recover_timeout_sec + 1.0)

        # restore normal backend behavior and ensure a successful pass closes the breaker
        backend_mock.fetch_flight_details.side_effect = None
        backend_mock.fetch_flight_details.return_value = flight_summary

        response = client.get("/api/v1/suggest?q=UA123&providers=flightaware")
        assert response.status_code == 200
        spy.assert_called_once()  # half-open allowed a trial call through

        # subsequent requests should also succeed (breaker back to closed)
        for _ in range(settings.providers.flightaware.circuit_breaker_failure_threshold):
            response = client.get("/api/v1/suggest?providers=flightaware&q=UA123")
            assert response.status_code == 200
