"""Utilities for the flight aware backend"""

import datetime
import logging
import re
from typing import Any

from pydantic import HttpUrl
from merino.providers.suggest.flightaware.backends.protocol import (
    AirportDetails,
    FlightScheduleSegment,
    FlightStatus,
    FlightSummary,
)
from merino.configs import settings

logger = logging.getLogger(__name__)

LANDING_PAGE_URL: str = settings.flightaware.landing_page_url
FLIGHT_NUM_PATTERN_1 = re.compile(
    r"^[A-Za-z]{1,3}\s*\d{1,5}$", re.IGNORECASE
)  # matches 1-3 letters followed by 1-5 digits e.g 'UAL101', 'A1234'.
FLIGHT_NUM_PATTERN_2 = re.compile(
    r"^\d\s*[A-Za-z]\s*\d{1,4}$", re.IGNORECASE
)  # matches 1 digit, 1 letter, followed by 1-4 digits e.g '3U 1001'


# TODO this will be implemented in DISCO-3736
def derive_flight_status(flight: dict) -> FlightStatus:
    """Determine a flight's operational status from its timestamp fields."""
    return FlightStatus.EN_ROUTE  # hardcoded for now


def parse_timestamp(timestamp: str | None) -> datetime.datetime | None:
    """Parse an ISO 8601 UTC timestamp string into a datetime object."""
    if not timestamp:
        return None
    try:
        return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def minutes_from_now(timestamp: str | None, now: datetime.datetime) -> float:
    """Return the absolute difference in minutes between the given timestamp and now."""
    dt = parse_timestamp(timestamp)
    return abs((dt - now).total_seconds()) / 60 if dt else float("inf")


def is_within_two_hours(timestamp: str | None, now: datetime.datetime) -> bool:
    """Return True if the timestamp is within 2 hours of now."""
    dt = parse_timestamp(timestamp)
    return abs(now - dt) <= datetime.timedelta(hours=2) if dt else False


def pick_best_flights(flights: list[dict], limit: int = 3) -> list[dict]:
    """Select up to `limit` flight instances based on status and proximity to now.

    Flights from these statuses are included:
    - En Route - all eligible, top priority
    - Scheduled/Delayed - all eligible, sorted by proximity
    - Arrived - only the most recent (within 2h)
    - Cancelled - only the most recent (within 2h)

    All candidates are sorted by their time distance from now and top-N are returned.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    priority_order = {
        FlightStatus.EN_ROUTE: 0,
        FlightStatus.SCHEDULED: 1,
        FlightStatus.DELAYED: 1,
        FlightStatus.ARRIVED: 2,
        FlightStatus.CANCELLED: 3,
    }

    # Final list of all eligible flights with _distance_minutes annotated
    candidates = []
    arrived_candidates = []
    cancelled_candidates = []

    for flight in flights:
        status: FlightStatus = derive_flight_status(flight)

        if status == FlightStatus.EN_ROUTE:
            # Force it to the top by assigning small negative distance
            flight["_distance_minutes"] = -1
            candidates.append(flight)

        elif status == FlightStatus.SCHEDULED or status == FlightStatus.DELAYED:
            timestamp = flight.get("estimated_out") or flight.get("scheduled_out")
            if timestamp:
                flight["_distance_minutes"] = minutes_from_now(timestamp, now)
                candidates.append(flight)

        elif status == FlightStatus.ARRIVED:
            timestamp = flight.get("actual_on") or flight.get("actual_in")
            if timestamp and is_within_two_hours(timestamp, now):
                flight["_distance_minutes"] = minutes_from_now(timestamp, now)
                arrived_candidates.append(flight)

        elif status == FlightStatus.CANCELLED:
            timestamp = flight.get("scheduled_out")
            if timestamp and is_within_two_hours(timestamp, now):
                flight["_distance_minutes"] = minutes_from_now(timestamp, now)
                cancelled_candidates.append(flight)

    if arrived_candidates:
        closest_arrived = min(arrived_candidates, key=lambda f: f["_distance_minutes"])
        candidates.append(closest_arrived)

    if cancelled_candidates:
        closest_cancelled = min(cancelled_candidates, key=lambda f: f["_distance_minutes"])
        candidates.append(closest_cancelled)

    # Sort by distance to now
    candidates.sort(
        key=lambda f: (f["_distance_minutes"], priority_order[derive_flight_status(f)])
    )

    return candidates[:limit]


def build_flight_summary(flight: Any, normalized_query: str) -> FlightSummary | None:
    """Build and return a flight summary from the flight response"""
    try:
        flight_number = normalized_query

        destination_code = flight["destination"]["code_iata"]
        destination_city = flight["destination"]["city"]

        origin_code = flight["origin"]["code_iata"]
        origin_city = flight["origin"]["city"]

        destination = AirportDetails(code=destination_code, city=destination_city)
        origin = AirportDetails(code=origin_code, city=origin_city)

        scheduled_departure = flight["scheduled_out"]
        estimated_departure = flight["estimated_out"]

        scheduled_arrival = flight["scheduled_in"]
        estimated_arrival = flight["estimated_in"]

        departure = FlightScheduleSegment(
            scheduled_time=scheduled_departure, estimated_time=estimated_departure
        )
        arrival = FlightScheduleSegment(
            scheduled_time=scheduled_arrival, estimated_time=estimated_arrival
        )

        status = flight["status"]  # TODO would change to use derive_flight_status in DISCO-3736
        progress_percent = flight["progress_percent"]

        url = get_live_url(normalized_query, flight)

        # TODO
        # delayed_until = ""
        # time_left_minutes =

        return FlightSummary(
            flight_number=flight_number,
            destination=destination,
            origin=origin,
            departure=departure,
            arrival=arrival,
            status=status,
            progress_percent=progress_percent,
            url=url,
        )

    except (KeyError, IndexError, TypeError):
        logger.warning(f"Flightaware response json has incorrect shape: {flight}")
        return None


def get_live_url(query: str, flight: Any) -> HttpUrl:
    """Return the FlightAware live tracking URL for the queried flight.

    If the query does not match the primary IATA ident of the flight (i.e., it's a codeshare),
    this function attempts to resolve the correct ICAO ident using the codeshare mapping.
    If a matching codeshare is found, the corresponding ident is used to construct the URL.
    Otherwise, the primary ICAO ident for the flight is used.
    """
    if query != flight["ident_iata"]:
        codeshares_iata = flight["codeshares_iata"]
        codeshares_icao = flight["codeshares"]

        if codeshares_iata and codeshares_icao:
            codeshare_map = codeshare_map = dict(zip(codeshares_iata, codeshares_icao))

            if query in codeshare_map:
                return HttpUrl(LANDING_PAGE_URL.format(ident=codeshare_map.get(query)))

    return HttpUrl(LANDING_PAGE_URL.format(ident=flight["ident_icao"]))


def is_valid_flight_number_pattern(query: str) -> bool:
    """Return true if flight number matches either of the two valid flight regex patterns"""
    return bool(FLIGHT_NUM_PATTERN_1.match(query) or FLIGHT_NUM_PATTERN_2.match(query))
