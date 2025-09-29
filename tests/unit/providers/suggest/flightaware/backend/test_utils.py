# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Flightaware utils module."""

import datetime
from unittest.mock import patch
from pydantic import HttpUrl
import pytest

from merino.providers.suggest.flightaware.backends.protocol import (
    AirportDetails,
    FlightScheduleSegment,
    FlightStatus,
    FlightSummary,
)
from merino.providers.suggest.flightaware.backends.utils import (
    build_flight_summary,
    get_live_url,
    is_valid_flight_number_pattern,
    is_within_two_hours,
    minutes_from_now,
    parse_timestamp,
    pick_best_flights,
)

import merino.providers.suggest.flightaware.backends.utils as utils


@pytest.mark.parametrize(
    "ts, expected",
    [
        (
            "2025-09-29T12:34:56Z",
            datetime.datetime(2025, 9, 29, 12, 34, 56, tzinfo=datetime.timezone.utc),
        ),
        (
            "2025-09-29T12:34:56+00:00",
            datetime.datetime(2025, 9, 29, 12, 34, 56, tzinfo=datetime.timezone.utc),
        ),
        (None, None),
        ("", None),
        ("not-a-timestamp", None),
    ],
)
def test_parse_timestamp(ts, expected):
    """Ensure parse_timestamp correctly parses valid ISO-8601 UTC strings and returns None for invalid or empty input."""
    assert parse_timestamp(ts) == expected


@pytest.mark.parametrize(
    "description, timestamp, now, expected",
    [
        (
            "future timestamp 30 minutes later",
            "2025-09-29T12:30:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            30.0,
        ),
        (
            "past timestamp 30 minutes earlier",
            "2025-09-29T11:30:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            30.0,
        ),
        (
            "same timestamp as now",
            "2025-09-29T12:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            0.0,
        ),
        (
            "None input returns infinity",
            None,
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            float("inf"),
        ),
        (
            "invalid string returns infinity",
            "not-a-timestamp",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            float("inf"),
        ),
    ],
)
def test_minutes_from_now(description, timestamp, now, expected):
    """Verify minutes_from_now returns the absolute difference in minutes, or infinity for None/invalid timestamps."""
    result = minutes_from_now(timestamp, now)
    assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    "description, timestamp, now, expected",
    [
        (
            "timestamp exactly now",
            "2025-09-29T12:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp 1 hour in the future",
            "2025-09-29T13:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp 1 hour in the past",
            "2025-09-29T11:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp exactly 2 hours in the future",
            "2025-09-29T14:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp exactly 2 hours in the past",
            "2025-09-29T10:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp just over 2 hours in the future",
            "2025-09-29T14:01:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            False,
        ),
        (
            "timestamp just over 2 hours in the past",
            "2025-09-29T09:59:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            False,
        ),
        (
            "None input",
            None,
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            False,
        ),
        (
            "invalid timestamp string",
            "not-a-timestamp",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            False,
        ),
    ],
)
def test_is_within_two_hours(description, timestamp, now, expected):
    """Check that is_within_two_hours correctly detects timestamps within 2 hours of now."""
    result = is_within_two_hours(timestamp, now)
    assert result == expected, f"Failed: {description}"


def test_build_flight_summary_valid():
    """Confirm build_flight_summary returns a valid FlightSummary for a complete flight dict."""
    flight = {
        "ident_iata": "UA123",
        "ident_icao": "UAL123",
        "codeshares_iata": [],
        "codeshares": [],
        "destination": {"code_iata": "EWR", "city": "Newark"},
        "origin": {"code_iata": "SFO", "city": "San Francisco"},
        "scheduled_out": "2025-09-29T12:00:00Z",
        "estimated_out": "2025-09-29T12:05:00Z",
        "scheduled_in": "2025-09-29T16:00:00Z",
        "estimated_in": "2025-09-29T16:05:00Z",
        "status": "En Route",
        "progress_percent": 50,
    }

    summary = build_flight_summary(flight, normalized_query="UA123")

    assert isinstance(summary, FlightSummary)
    assert summary.flight_number == "UA123"
    assert summary.destination == AirportDetails(code="EWR", city="Newark")
    assert summary.origin == AirportDetails(code="SFO", city="San Francisco")
    assert summary.departure == FlightScheduleSegment(
        scheduled_time="2025-09-29T12:00:00Z", estimated_time="2025-09-29T12:05:00Z"
    )
    assert summary.arrival == FlightScheduleSegment(
        scheduled_time="2025-09-29T16:00:00Z", estimated_time="2025-09-29T16:05:00Z"
    )
    assert summary.status == "En Route"
    assert summary.progress_percent == 50
    assert summary.url == HttpUrl("https://www.flightaware.com/live/flight/UAL123")


def test_build_flight_summary_with_codeshare():
    """Confirm build_flight_summary resolves codeshare queries to the correct ICAO ident in the live URL."""
    flight = {
        "ident_iata": "UA123",
        "ident_icao": "UAL123",
        "codeshares_iata": ["AC9876"],
        "codeshares": ["ACA9876"],
        "destination": {"code_iata": "EWR", "city": "Newark"},
        "origin": {"code_iata": "SFO", "city": "San Francisco"},
        "scheduled_out": "2025-09-29T12:00:00Z",
        "estimated_out": "2025-09-29T12:05:00Z",
        "scheduled_in": "2025-09-29T16:00:00Z",
        "estimated_in": "2025-09-29T16:05:00Z",
        "status": "En Route",
        "progress_percent": 50,
    }

    summary = build_flight_summary(flight, normalized_query="AC9876")

    assert isinstance(summary, FlightSummary)
    assert summary.url == HttpUrl("https://www.flightaware.com/live/flight/ACA9876")


def test_build_flight_summary_missing_key_returns_none(caplog):
    """Ensure build_flight_summary returns None and logs a warning when required fields are missing."""
    flight = {
        # missing destination
        "origin": {"code_iata": "SFO", "city": "San Francisco"},
        "codeshares_iata": [],
        "codeshares": [],
        "scheduled_out": "2025-09-29T12:00:00Z",
        "estimated_out": "2025-09-29T12:05:00Z",
        "scheduled_in": "2025-09-29T16:00:00Z",
        "estimated_in": "2025-09-29T16:05:00Z",
        "status": "Scheduled",
        "progress_percent": 0,
    }

    result = build_flight_summary(flight, normalized_query="UA123")
    assert result is None
    assert "incorrect shape" in caplog.text


def test_build_flight_summary_invalid_type_returns_none(caplog):
    """Ensure build_flight_summary returns None and logs a warning when input is not a dict."""
    flight = "not-a-dict"
    result = build_flight_summary(flight, normalized_query="UA123")
    assert result is None
    assert "incorrect shape" in caplog.text


@pytest.mark.parametrize(
    "description, query, flight, expected",
    [
        (
            "query matches primary IATA ident - fall back to ICAO",
            "UA123",
            {
                "ident_iata": "UA123",
                "ident_icao": "UAL123",
                "codeshares_iata": ["AC9876"],
                "codeshares": ["ACA9876"],
            },
            HttpUrl("https://www.flightaware.com/live/flight/UAL123"),
        ),
        (
            "query matches codeshare AC9876 - resolves to ACA9876",
            "AC9876",
            {
                "ident_iata": "UA123",
                "ident_icao": "UAL123",
                "codeshares_iata": ["AC9876", "LH4321"],
                "codeshares": ["ACA9876", "DLH4321"],
            },
            HttpUrl("https://www.flightaware.com/live/flight/ACA9876"),
        ),
        (
            "query matches codeshare LH4321 - resolves to DLH4321",
            "LH4321",
            {
                "ident_iata": "UA123",
                "ident_icao": "UAL123",
                "codeshares_iata": ["AC9876", "LH4321"],
                "codeshares": ["ACA9876", "DLH4321"],
            },
            HttpUrl("https://www.flightaware.com/live/flight/DLH4321"),
        ),
        (
            "query not in codeshares - fall back to ICAO",
            "SOMEOTHER",
            {
                "ident_iata": "UA123",
                "ident_icao": "UAL123",
                "codeshares_iata": ["AC9876"],
                "codeshares": ["ACA9876"],
            },
            HttpUrl("https://www.flightaware.com/live/flight/UAL123"),
        ),
        (
            "empty codeshares - should fall back to ICAO",
            "AC9876",
            {
                "ident_iata": "UA123",
                "ident_icao": "UAL123",
                "codeshares_iata": [],
                "codeshares": [],
            },
            HttpUrl("https://www.flightaware.com/live/flight/UAL123"),
        ),
    ],
)
def test_get_live_url(description, query, flight, expected):
    """Verify get_live_url builds the correct FlightAware URL."""
    result: HttpUrl = get_live_url(query, flight)
    assert result == expected, f"Failed: {description}"


@pytest.fixture
def fixed_now():
    """Provide a fixed UTC datetime (2025-09-29T12:00:00Z) for testing."""
    return datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc)


def test_pick_best_flight_en_route_always_top():
    """Check that en route flights are always prioritized to the top regardless of other flights."""
    flights = [
        {"id": "scheduled", "scheduled_out": "2025-09-29T12:30:00Z"},
        {"id": "enroute"},
    ]

    def fake_status(flight):
        return FlightStatus.EN_ROUTE if flight["id"] == "enroute" else FlightStatus.SCHEDULED

    with patch.object(utils, "derive_flight_status", side_effect=fake_status):
        results = pick_best_flights(flights, limit=2)

    assert results[0]["id"] == "enroute"


def test_pick_best_flight_scheduled_sorted_by_proximity(fixed_now):
    """Ensure scheduled flights are ordered by proximity to now, with nearer flights first."""
    flights = [
        {"id": "later", "scheduled_out": "2025-09-29T13:00:00Z"},
        {"id": "sooner", "scheduled_out": "2025-09-29T12:15:00Z"},
    ]

    with (
        patch.object(utils, "derive_flight_status", return_value=FlightStatus.SCHEDULED),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now

        results = pick_best_flights(flights, limit=2)

    assert [f["id"] for f in results] == ["sooner", "later"]


def test_pick_best_flight_arrived_included_if_within_two_hours(fixed_now):
    """Confirm arrived flights within the past 2 hours are included in results."""
    flights = [
        {"id": "arrived", "actual_on": "2025-09-29T11:30:00Z"},
    ]

    with (
        patch.object(utils, "derive_flight_status", return_value=FlightStatus.ARRIVED),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now

        results = pick_best_flights(flights, limit=1)

    assert results[0]["id"] == "arrived"
    assert "_distance_minutes" in results[0]


def test_pick_best_flight_cancelled_included_if_within_two_hours(fixed_now):
    """Confirm cancelled flights scheduled within the past 2 hours are included in results."""
    flights = [
        {"id": "cancelled", "scheduled_out": "2025-09-29T11:30:00Z"},
    ]

    with (
        patch.object(utils, "derive_flight_status", return_value=FlightStatus.CANCELLED),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now

        results = pick_best_flights(flights, limit=1)

    assert results[0]["id"] == "cancelled"
    assert "_distance_minutes" in results[0]


def test_pick_best_flight_arrived_prioritized_over_scheduled_if_closer_to_now(
    fixed_now,
):
    """Validate that an arrived flight closer to now is prioritized ahead of a scheduled flight further away."""
    flights = [
        # Scheduled 90 minutes from now
        {"id": "scheduled", "scheduled_out": "2025-09-29T13:30:00Z"},
        # Arrived 30 minutes ago
        {"id": "arrived", "actual_on": "2025-09-29T11:30:00Z"},
    ]

    def fake_status(f):
        if f["id"] == "scheduled":
            return FlightStatus.SCHEDULED
        if f["id"] == "arrived":
            return FlightStatus.ARRIVED

    with (
        patch.object(utils, "derive_flight_status", side_effect=fake_status),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now
        results = pick_best_flights(flights, limit=2)

    # Expect arrived (closer to now) before scheduled
    assert [f["id"] for f in results] == ["arrived", "scheduled"]


def test_pick_best_flights_mixed_statuses_prioritized(fixed_now):
    """Check that flights are prioritized in order: En Route > Scheduled > Arrived > Cancelled."""
    flights = [
        # En Route should always win
        {"id": "enroute"},
        # Scheduled flight 30m from now
        {"id": "scheduled", "scheduled_out": "2025-09-29T12:30:00Z"},
        # Arrived flight 30m ago (within 2h, but after scheduled)
        {"id": "arrived", "actual_on": "2025-09-29T11:30:00Z"},
        # Cancelled flight 1h ago (within 2h, but lowest priority)
        {"id": "cancelled", "scheduled_out": "2025-09-29T11:00:00Z"},
    ]

    def fake_status(f):
        if f["id"] == "enroute":
            return FlightStatus.EN_ROUTE
        if f["id"] == "scheduled":
            return FlightStatus.SCHEDULED
        if f["id"] == "arrived":
            return FlightStatus.ARRIVED
        if f["id"] == "cancelled":
            return FlightStatus.CANCELLED

    with (
        patch.object(utils, "derive_flight_status", side_effect=fake_status),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now
        results = pick_best_flights(flights, limit=4)

    assert [f["id"] for f in results] == [
        "enroute",
        "scheduled",
        "arrived",
        "cancelled",
    ]


def test_pick_best_flight_limit_respected(fixed_now):
    """Ensure the pick_best_flights function respects the limit and only returns up to N flights."""
    flights = [
        {"id": "f1", "scheduled_out": "2025-09-29T12:00:00Z"},
        {"id": "f2", "scheduled_out": "2025-09-29T12:05:00Z"},
        {"id": "f3", "scheduled_out": "2025-09-29T12:10:00Z"},
    ]

    with (
        patch.object(utils, "derive_flight_status", return_value=FlightStatus.SCHEDULED),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now

        results = pick_best_flights(flights, limit=2)

    assert len(results) == 2


def test_multiple_arrived_only_most_recent_kept(fixed_now):
    """Ensure that only the most recent ARRIVED flight (closest to now) is returned."""
    flights = [
        {"id": "arrived1", "actual_on": "2025-09-29T11:00:00Z"},  # 1h ago
        {"id": "arrived2", "actual_on": "2025-09-29T11:30:00Z"},  # 30m ago (closer)
    ]

    def fake_status(f):
        return FlightStatus.ARRIVED

    with (
        patch.object(utils, "derive_flight_status", side_effect=fake_status),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_dt,
    ):
        mock_dt.now.return_value = fixed_now
        results = utils.pick_best_flights(flights, limit=3)

    # Only one ARRIVED flight should be present, and it should be the closer one
    arrived_ids = [f["id"] for f in results if fake_status(f) == FlightStatus.ARRIVED]
    assert arrived_ids == ["arrived2"]


def test_multiple_cancelled_only_most_recent_kept(fixed_now):
    """Ensure that only the most recent CANCELLED flight (closest to now) is returned."""
    flights = [
        {"id": "cancelled1", "scheduled_out": "2025-09-29T11:00:00Z"},  # 1h ago
        {
            "id": "cancelled2",
            "scheduled_out": "2025-09-29T11:30:00Z",
        },  # 30m ago (closer)
    ]

    def fake_status(f):
        return FlightStatus.CANCELLED

    with (
        patch.object(utils, "derive_flight_status", side_effect=fake_status),
        patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_dt,
    ):
        mock_dt.now.return_value = fixed_now
        results = utils.pick_best_flights(flights, limit=3)

    # Only one CANCELLED flight should be present, and it should be the closer one
    cancelled_ids = [f["id"] for f in results if fake_status(f) == FlightStatus.CANCELLED]
    assert cancelled_ids == ["cancelled2"]


@pytest.mark.parametrize(
    "description, query, expected",
    [
        # valid flight numbers
        ("2-letter code + 3-digit number", "UA123", True),
        ("3-letter code + 3-digit number", "ACA432", True),
        ("2-letter lowercase + 3-digit", "ua123", True),
        ("2-letter + space + 3-digit", "UA 123", True),
        ("2-letter + multiple spaces + 3-digit", "UA    123", True),
        ("2-char alphanumeric (3U) + 4-digit", "3U1001", True),
        ("2-char alphanumeric + space + 4-digit", "3U 1001", True),
        ("mixed case + spacing", "aC 701", True),
        ("single letter code", "A3101", True),
        # invalid flight numbers
        ("only digits", "123", False),
        ("too many letters", "UAAZ123", False),
        ("too many digits", "UA123456", False),
        ("symbols in code", "UA!123", False),
        ("empty string", "", False),
        ("only code, no number", "UA", False),
        ("only number, no code", "1234", False),
        ("space only", "   ", False),
    ],
)
def test_is_valid_flight_number_pattern(description, query, expected):
    """Test the is_valid_flight_number_pattern function against a range of inputs."""
    result = is_valid_flight_number_pattern(query)
    assert result == expected, f"Failed: {description} (input: '{query}')"
