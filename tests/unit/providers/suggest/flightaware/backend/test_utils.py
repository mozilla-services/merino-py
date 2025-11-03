# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Flightaware utils module."""

import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from pydantic import HttpUrl
import pytest

from merino.providers.suggest.flightaware.backends.protocol import (
    AirlineDetails,
    AirportDetails,
    FlightStatus,
    FlightSummary,
)
from merino.providers.suggest.flightaware.backends.utils import (
    build_flight_summary,
    calculate_time_left,
    get_airline_details,
    get_flight_number_from_query_if_valid,
    get_live_url,
    is_delayed,
    is_valid_flight_keyword_pattern,
    is_valid_flight_number_pattern,
    is_within_one_hour,
    minutes_from_now,
    parse_timestamp,
    pick_best_flights,
)

import merino.providers.suggest.flightaware.backends.utils as utils


@pytest.fixture
def fixed_now():
    """Provide a fixed UTC datetime (2025-09-29T12:00:00Z) for testing."""
    return datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def flight_with_codeshare():
    """Return a valid flight response with codeshares for testing"""
    return {
        "ident_iata": "UA123",
        "ident_icao": "UAL123",
        "codeshares_iata": ["AC9876"],
        "codeshares": ["ACA9876"],
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
        "status": "En Route",
        "progress_percent": 50,
    }


@pytest.mark.parametrize(
    "description, ts, tz, expected",
    [
        (
            "valid UTC timestamp with Z suffix, default UTC",
            "2025-09-29T12:34:56Z",
            None,
            datetime.datetime(2025, 9, 29, 12, 34, 56, tzinfo=datetime.timezone.utc),
        ),
        (
            "valid UTC timestamp with explicit +00:00 offset, default UTC",
            "2025-09-29T12:34:56+00:00",
            None,
            datetime.datetime(2025, 9, 29, 12, 34, 56, tzinfo=datetime.timezone.utc),
        ),
        (
            "convert UTC timestamp to New York local time",
            "2025-09-29T12:34:56Z",
            "America/New_York",
            datetime.datetime(2025, 9, 29, 8, 34, 56, tzinfo=ZoneInfo("America/New_York")),
        ),
        (
            "convert UTC timestamp to Berlin local time",
            "2025-09-29T12:34:56Z",
            "Europe/Berlin",
            datetime.datetime(2025, 9, 29, 14, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")),
        ),
        (
            "None input returns None",
            None,
            None,
            None,
        ),
        (
            "Unrecognized timezone returns None",
            "2025-09-29T12:34:56Z",
            "not-a-timezone",
            None,
        ),
        (
            "empty string returns None",
            "",
            None,
            None,
        ),
        (
            "invalid timestamp returns None",
            "not-a-timestamp",
            None,
            None,
        ),
    ],
)
def test_parse_timestamp(description, ts, tz, expected):
    """Ensure parse_timestamp correctly parses UTC strings, converts to local when tz provided, and handles invalid input."""
    result = parse_timestamp(ts, tz)
    assert result == expected, f"Failed: {description}"


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
            "timestamp exactly 1 hour in the future",
            "2025-09-29T13:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp exactly 1 hour in the past",
            "2025-09-29T11:00:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            True,
        ),
        (
            "timestamp just over 1 hour in the future",
            "2025-09-29T13:01:00Z",
            datetime.datetime(2025, 9, 29, 12, 0, tzinfo=datetime.timezone.utc),
            False,
        ),
        (
            "timestamp just over 1 hour in the past",
            "2025-09-29T10:59:00Z",
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
def test_is_within_one_hour(description, timestamp, now, expected):
    """Check that is_within_one_hour correctly detects timestamps within 2 hours of now."""
    result = is_within_one_hour(timestamp, now)
    assert result == expected, f"Failed: {description}"


def test_build_flight_summary_valid(flight_with_codeshare):
    """Confirm build_flight_summary returns a valid FlightSummary with local timezone conversions."""
    summary = build_flight_summary(flight_with_codeshare, normalized_query="UA123")

    assert isinstance(summary, FlightSummary)
    assert summary.flight_number == "UA123"
    assert summary.destination == AirportDetails(code="EWR", city="Newark")
    assert summary.origin == AirportDetails(code="SFO", city="San Francisco")

    # departure times should be localized to San Francisco time
    assert summary.departure.scheduled_time == datetime.datetime(
        2025, 9, 29, 5, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")
    )
    assert summary.departure.estimated_time == datetime.datetime(
        2025, 9, 29, 5, 5, 0, tzinfo=ZoneInfo("America/Los_Angeles")
    )

    # arrival times should be localized to New York time
    assert summary.arrival.scheduled_time == datetime.datetime(
        2025, 9, 29, 12, 0, 0, tzinfo=ZoneInfo("America/New_York")
    )
    assert summary.arrival.estimated_time == datetime.datetime(
        2025, 9, 29, 12, 5, 0, tzinfo=ZoneInfo("America/New_York")
    )

    assert summary.status == "Scheduled"
    assert summary.progress_percent == 50
    assert summary.url == HttpUrl("https://www.flightaware.com/live/flight/UAL123")

    assert summary.airline.code == "UA"
    assert summary.airline.name == "United Airlines"
    assert summary.airline.color == "#005DAA"


def test_build_flight_summary_with_codeshare(flight_with_codeshare):
    """Confirm build_flight_summary resolves codeshare queries to the correct ICAO ident in the live URL."""
    summary = build_flight_summary(flight_with_codeshare, normalized_query="AC9876")

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


def test_pick_best_flight_arrived_included_if_within_one_hour(fixed_now):
    """Confirm arrived flights within the past 1 hours are included in results."""
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


def test_pick_best_flight_cancelled_included_if_within_one_hour(fixed_now):
    """Confirm cancelled flights scheduled within the past 1 hour are included in results."""
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
        # Arrived flight 30m ago (within 1h, but after scheduled)
        {"id": "arrived", "actual_on": "2025-09-29T11:30:00Z"},
        # Cancelled flight 1h ago (within 1h, but lowest priority)
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


@pytest.mark.parametrize(
    "description, flight, expected",
    [
        (
            "cancelled flight takes priority even if other fields present",
            {
                "cancelled": True,
                "actual_out": "2025-09-29T12:00:00Z",
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": 1800,
            },
            FlightStatus.CANCELLED,
        ),
        (
            "en route flight (actual_out set, no actual_on)",
            {
                "cancelled": False,
                "actual_out": "2025-09-29T12:00:00Z",
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": 0,
            },
            FlightStatus.EN_ROUTE,
        ),
        (
            "arrived flight (actual_on set, actual_in missing)",
            {
                "cancelled": False,
                "actual_out": "2025-09-29T12:00:00Z",
                "actual_on": "2025-09-29T14:00:00Z",
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "actual_in": None,
                "departure_delay": 1800,
            },
            FlightStatus.ARRIVED,
        ),
        (
            "arrived flight (actual_in set, actual_on missing)",
            {
                "cancelled": False,
                "actual_out": "2025-09-29T12:00:00Z",
                "actual_on": None,
                "actual_in": "2025-09-29T14:10:00Z",
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": 0,
            },
            FlightStatus.ARRIVED,
        ),
        (
            "scheduled flight (no actual_out, no delay)",
            {
                "cancelled": False,
                "actual_out": None,
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": None,
            },
            FlightStatus.SCHEDULED,
        ),
        (
            "scheduled but delayed flight (no actual_out, delay > 15 minutes)",
            {
                "cancelled": False,
                "actual_out": None,
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": 1800,
            },
            FlightStatus.DELAYED,
        ),
        (
            "scheduled but on time (no actual_out, delay < 15 minutes)",
            {
                "cancelled": False,
                "actual_out": None,
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": "2025-09-29T14:10:00Z",
                "estimated_out": "2025-09-29T14:10:00Z",
                "departure_delay": 600,
            },
            FlightStatus.SCHEDULED,
        ),
        (
            "unknown status - missing fields",
            {
                "cancelled": False,
                "actual_out": None,
                "actual_on": None,
                "actual_in": None,
                "scheduled_out": None,
                "estimated_out": None,
                "departure_delay": None,
            },
            FlightStatus.UNKNOWN,
        ),
    ],
)
def test_derive_flight_status(description, flight, expected):
    """Verify derive_flight_status returns the correct FlightStatus for each scenario."""
    result = utils.derive_flight_status(flight)
    assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    "description, flight, expected",
    [
        (
            "arrived flight with actual_in present returns 0",
            {
                "actual_out": "2025-09-29T10:00:00Z",
                "actual_in": "2025-09-29T11:30:00Z",
                "scheduled_in": "2025-09-29T12:30:00Z",
            },
            0,
        ),
        (
            "arrived flight with actual_on present returns 0",
            {
                "actual_out": "2025-09-29T10:00:00Z",
                "actual_on": "2025-09-29T11:45:00Z",
                "scheduled_in": "2025-09-29T12:30:00Z",
            },
            0,
        ),
        (
            "not departed (no actual_out) returns None",
            {
                "actual_out": None,
                "scheduled_in": "2025-09-29T14:00:00Z",
            },
            None,
        ),
        (
            "en route with estimated_in returns minutes until ETA",
            {
                "actual_out": "2025-09-29T11:00:00Z",
                "estimated_in": "2025-09-29T13:00:00Z",  # 1 hour after fixed_now
            },
            60,
        ),
        (
            "en route with scheduled_in returns minutes until scheduled arrival",
            {
                "actual_out": "2025-09-29T11:00:00Z",
                "scheduled_in": "2025-09-29T13:30:00Z",  # 1.5 hours after fixed_now
            },
            90,
        ),
        (
            "past arrival time returns 0",
            {
                "actual_out": "2025-09-29T10:00:00Z",
                "estimated_in": "2025-09-29T11:00:00Z",  # 1 hour before fixed_now
            },
            0,
        ),
        (
            "en route but no estimated_in or scheduled_in returns None",
            {
                "actual_out": "2025-09-29T11:00:00Z",
            },
            None,
        ),
    ],
)
def test_calculate_time_left(description, flight, expected, fixed_now):
    """Test calculate_time_left across all lifecycle scenarios."""
    with patch.object(utils.datetime, "datetime", wraps=datetime.datetime) as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        result = calculate_time_left(flight)
        assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    "description, flight, expected",
    [
        (
            "no departure_delay field returns False",
            {},
            False,
        ),
        (
            "departure_delay is None returns False",
            {"departure_delay": None},
            False,
        ),
        (
            "departure_delay less than 15 minutes returns False",
            {"departure_delay": 600},  # 10 minutes
            False,
        ),
        (
            "departure_delay equal to 15 minutes returns False",
            {"departure_delay": 900},  # exactly 15 minutes
            False,
        ),
        (
            "departure_delay greater than 15 minutes returns True",
            {"departure_delay": 1200},  # 20 minutes
            True,
        ),
    ],
)
def test_is_delayed(description, flight, expected):
    """Verify is_delayed correctly detects delays above 15 minutes."""
    result = is_delayed(flight)
    assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    "description, query, expected",
    [
        ("single word + digits", "Delta 101", True),
        ("two words + digits", "United Airlines 101", True),
        ("three words + digits", "Air Canada Express 200", True),
        ("max five words + digits", "Lufthansa Cargo Regional Flight 12345", True),
        ("mixed case words + digits", "aIr FrAnCe 789", True),
        ("extra spaces between words allowed", "British    Airways    555", True),
        ("lowercase airline + digits", "air canada 250", True),
        ("uppercase airline + digits", "AIR CANADA 250", True),
        ("only airline name, no digits", "United Airlines", False),
        ("no airline name, only digits", "12345", False),
        ("too many words before digits", "This Has Too Many Words Before 123", False),
        ("contains symbols in airline name", "Air-Canada 123", False),
        ("contains special character in digits", "United 12A3", False),
        ("empty string", "", False),
        ("spaces only", "   ", False),
        ("leading digits not allowed", "123 United Airlines", False),
    ],
)
def test_is_valid_flight_keyword_pattern(description, query, expected):
    """Test is_valid_flight_keyword_pattern with valid and invalid airline + flight number combinations."""
    result = is_valid_flight_keyword_pattern(query)
    assert result == expected, f"Failed: {description} (input: '{query}')"


@pytest.mark.parametrize(
    "description, query, mapping, expected",
    [
        ("2-letter + digits", "UA123", {}, "UA123"),
        ("with space between letters and digits", "AA 101", {}, "AA101"),
        ("lowercase input normalized to uppercase", "ac432", {}, "AC432"),
        ("3-letter airline + digits", "UAL987", {}, "UAL987"),
        ("alphanumeric airline code pattern", "3U1001", {}, "3U1001"),
        (
            "airline keyword pattern with mapping",
            "Air Canada 250",
            {"air canada": "AC"},
            "AC250",
        ),
        (
            "mixed case keyword airline name",
            "aIr FrAnCe 789",
            {"air france": "AF"},
            "AF789",
        ),
        (
            "keyword query with multiple spaces normalized",
            "British   Airways   555",
            {"british airways": "BA"},
            "BA555",
        ),
        ("no matching mapping for keyword query", "Air Something 400", {}, None),
        ("invalid flight number format", "1234", {}, None),
        ("keyword without digits", "Air Canada", {"air canada": "AC"}, None),
        ("invalid keyword pattern", "Air Canada XYZ", {"air canada": "AC"}, None),
        ("empty string", "", {}, None),
        ("spaces only", "   ", {}, None),
        ("garbage input", "@@@@", {}, None),
    ],
)
def test_get_flight_number_from_query_if_valid(description, query, mapping, expected):
    """Test get_flight_number_from_query_if_valid with direct and keyword-based flight patterns."""
    with patch(
        "merino.providers.suggest.flightaware.backends.utils.NAME_TO_AIRLINE_CODE_MAPPING",
        mapping,
    ):
        result = get_flight_number_from_query_if_valid(query)
        assert result == expected, f"Failed: {description} (input: '{query}')"


@pytest.mark.parametrize(
    "description, flight_number, expected_code, expected_name, expected_color",
    [
        ("valid 2-letter IATA code", "AA123", "AA", "American Airlines", "#cc0000"),
        (
            "valid 3-letter ICAO code fallback when IATA not matched",
            "UAL789",
            "UAL",
            "United Airlines",
            "#003366",
        ),
        ("unknown airline code returns None values", "ZZ999", None, None, None),
        ("invalid short flight number", "A123", None, None, None),
        ("nonexistent airline code in valid format", "XY123", None, None, None),
        ("name and code not in set/map", "TS123", None, None, None),
    ],
)
def test_get_airline_details(
    description, flight_number, expected_code, expected_name, expected_color
):
    """Verify get_airline_details correctly extracts valid IATA/ICAO codes and returns correct airline details."""
    mock_valid_codes = {"AA", "BA", "UAL", "AF"}
    mock_code_to_name = {
        "AA": {"name": "american airlines", "color": "#cc0000"},
        "BA": {"name": "british airways", "color": "#ABCDEF"},
        "UAL": {"name": "united airlines", "color": "#003366"},
        "AF": {"name": "air france", "color": "#ff5000"},
    }

    with (
        patch(
            "merino.providers.suggest.flightaware.backends.utils.VALID_AIRLINE_CODES",
            mock_valid_codes,
        ),
        patch(
            "merino.providers.suggest.flightaware.backends.utils.AIRLINE_CODE_TO_NAME_MAPPING",
            mock_code_to_name,
        ),
    ):
        result = get_airline_details(flight_number)

    assert isinstance(result, AirlineDetails)
    assert result.code == expected_code, f"Failed code match: {description}"
    assert result.name == expected_name, f"Failed name match: {description}"
    assert result.color == expected_color
    assert result.icon is None
