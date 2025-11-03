"""Utilities for the flight aware backend"""

import datetime
import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import HttpUrl
from merino.providers.suggest.flightaware.backends.airline_mappings import (
    AIRLINE_CODE_TO_NAME_MAPPING,
    NAME_TO_AIRLINE_CODE_MAPPING,
    VALID_AIRLINE_CODES,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    AirlineDetails,
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
FLIGHT_KEYWORD_PATTERN = pattern = re.compile(
    r"^[A-Za-z]+(?:\s+[a-z]+){0,4}\s+\d{1,5}$", re.IGNORECASE
)
# matches 1-5 words, followed by 1-5 digits e.g united airlines 100, air canada 250


def derive_flight_status(flight: dict) -> FlightStatus:
    """Derive a stable, backend-calculated flight status from AeroAPI fields.

    This method determines a flight's operational status using a combination
    of lifecycle timestamps and delay information, instead of relying on
    AeroAPI's free-form status string. The mapping is:

    - CANCELLED  : Flight is explicitly marked as cancelled by the AeroAPI flag.
    - EN_ROUTE   : Flight has an actual departure time (`actual_out`) but
                   no recorded arrival time (`actual_on`).
    - ARRIVED    : Flight has an arrival timestamp (`actual_on` or `actual_in`).
    - DELAYED    : Flight has not departed (`actual_out` is None) and
                   `departure_delay` is greater than 15 minutes.
    - SCHEDULED  : Flight has not departed (`actual out` is None and `scheduled_out` is set) and either
                   - `departure_delay` is None, or
                   - `departure_delay` is 15 minutes or less (on time or early).
    - UNKNOWN    : Any case not covered by the above.
    """
    actual_out = flight.get("actual_out")
    actual_on = flight.get("actual_on")
    actual_in = flight.get("actual_in")
    scheduled_out = flight.get("scheduled_out")
    estimated_out = flight.get("estimated_out")

    if flight.get("cancelled"):
        return FlightStatus.CANCELLED

    elif actual_out and not actual_on and not actual_in:
        return FlightStatus.EN_ROUTE
    elif actual_on or actual_in:
        return FlightStatus.ARRIVED

    elif actual_out is None:
        if is_delayed(flight):
            return FlightStatus.DELAYED
        elif scheduled_out or estimated_out:
            return FlightStatus.SCHEDULED
    return FlightStatus.UNKNOWN


def parse_timestamp(
    timestamp: str | None, timezone: str | None = None
) -> datetime.datetime | None:
    """Parse an ISO 8601 UTC timestamp string into a datetime object.

    - If timezone is None, return a UTC datetime (default).
    - If timezone (an IANA time zone string such as "America/New_York") is provided,
    return the datetime converted to that timezone.
    """
    if not timestamp:
        return None
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if timezone:
            return dt.astimezone(ZoneInfo(timezone))
        return dt
    except (ValueError, ZoneInfoNotFoundError):
        return None


def minutes_from_now(timestamp: str | None, now: datetime.datetime) -> float:
    """Return the absolute difference in minutes between the given timestamp and now."""
    dt = parse_timestamp(timestamp)
    return abs((dt - now).total_seconds()) / 60 if dt else float("inf")


def is_within_one_hour(timestamp: str | None, now: datetime.datetime) -> bool:
    """Return True if the timestamp is within 1 hour of now."""
    dt = parse_timestamp(timestamp)
    return abs(now - dt) <= datetime.timedelta(hours=1) if dt else False


def pick_best_flights(flights: list[dict], limit: int = 2) -> list[dict]:
    """Select up to `limit` flight instances based on status and proximity to now.

    Flights from these statuses are included:
    - En Route - all eligible, top priority
    - Scheduled/Delayed - all eligible, sorted by proximity
    - Arrived - only the most recent (within 1h)
    - Cancelled - only the most recent (within 1h)

    All candidates are sorted by their time distance from now and top-N are returned.
    Flights with unknown statuses are skipped.
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
        flight["_status"] = status

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
            if timestamp and is_within_one_hour(timestamp, now):
                flight["_distance_minutes"] = minutes_from_now(timestamp, now)
                arrived_candidates.append(flight)

        elif status == FlightStatus.CANCELLED:
            timestamp = flight.get("scheduled_out")
            if timestamp and is_within_one_hour(timestamp, now):
                flight["_distance_minutes"] = minutes_from_now(timestamp, now)
                cancelled_candidates.append(flight)
        else:
            continue

    if arrived_candidates:
        closest_arrived = min(arrived_candidates, key=lambda f: f["_distance_minutes"])
        candidates.append(closest_arrived)

    if cancelled_candidates:
        closest_cancelled = min(cancelled_candidates, key=lambda f: f["_distance_minutes"])
        candidates.append(closest_cancelled)

    # Sort by distance to now
    candidates.sort(key=lambda f: (f["_distance_minutes"], priority_order[f["_status"]]))

    return candidates[:limit]


def build_flight_summary(flight: dict, normalized_query: str) -> FlightSummary | None:
    """Build and return a flight summary from the flight response"""
    try:
        flight_number = normalized_query

        destination_code = flight["destination"]["code_iata"]
        destination_city = flight["destination"]["city"]
        destination_timezone = flight["destination"]["timezone"]

        origin_code = flight["origin"]["code_iata"]
        origin_city = flight["origin"]["city"]
        origin_timezone = flight["origin"]["timezone"]

        destination = AirportDetails(code=destination_code, city=destination_city)
        origin = AirportDetails(code=origin_code, city=origin_city)

        # return local timezone for departure and arrival times
        scheduled_departure = parse_timestamp(flight["scheduled_out"], origin_timezone)
        estimated_departure = parse_timestamp(flight["estimated_out"], origin_timezone)

        scheduled_arrival = parse_timestamp(flight["scheduled_in"], destination_timezone)
        estimated_arrival = parse_timestamp(flight["estimated_in"], destination_timezone)

        departure = FlightScheduleSegment(
            scheduled_time=scheduled_departure, estimated_time=estimated_departure
        )
        arrival = FlightScheduleSegment(
            scheduled_time=scheduled_arrival, estimated_time=estimated_arrival
        )

        airline = get_airline_details(flight_number)

        status = derive_flight_status(flight)
        progress_percent = flight.get("progress_percent") or 0
        delayed = is_delayed(flight)

        url = get_live_url(normalized_query, flight)
        time_left_minutes = calculate_time_left(flight)

        return FlightSummary(
            flight_number=flight_number,
            destination=destination,
            origin=origin,
            departure=departure,
            arrival=arrival,
            status=status,
            airline=airline,
            delayed=delayed,
            progress_percent=progress_percent,
            time_left_minutes=time_left_minutes,
            url=url,
        )

    except (KeyError, IndexError, TypeError):
        logger.warning(f"Flightaware response json has incorrect shape: {flight}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error parsing flightaware response: {e}")
        return None


def get_live_url(query: str, flight: dict) -> HttpUrl:
    """Return the FlightAware live tracking URL for the queried flight.

    If the query does not match the primary IATA ident of the flight (i.e., it's a codeshare),
    this function attempts to resolve the correct ICAO ident using the codeshare mapping.
    If a matching codeshare is found, the corresponding ident is used to construct the URL.
    Otherwise, the primary ICAO ident for the flight is used.
    """
    if query != flight.get("ident_iata"):
        codeshares_iata = flight.get("codeshares_iata")
        codeshares_icao = flight.get("codeshares")

        if codeshares_iata and codeshares_icao:
            codeshare_map = codeshare_map = dict(zip(codeshares_iata, codeshares_icao))

            if query in codeshare_map:
                return HttpUrl(LANDING_PAGE_URL.format(ident=codeshare_map.get(query)))

    return HttpUrl(LANDING_PAGE_URL.format(ident=flight["ident_icao"]))


def is_valid_flight_number_pattern(query: str) -> bool:
    """Return true if the query matches either of the two valid flight regex patterns"""
    return bool(FLIGHT_NUM_PATTERN_1.match(query) or FLIGHT_NUM_PATTERN_2.match(query))


def is_valid_flight_keyword_pattern(query: str) -> bool:
    """Return true if the query matches a valid flight keyword pattern"""
    return bool(FLIGHT_KEYWORD_PATTERN.match(query))


def get_flight_number_from_query_if_valid(query: str) -> str | None:
    """Return a processed flight number or None if a valid one doesn't exist"""
    flight_number = None
    if is_valid_flight_number_pattern(query):
        flight_number = query.replace(" ", "").upper()

    elif is_valid_flight_keyword_pattern(query):
        query_list = query.lower().split()
        digits = query_list[-1]
        airline_name = " ".join(query_list[: len(query_list) - 1])
        airline_code = NAME_TO_AIRLINE_CODE_MAPPING.get(airline_name)

        if airline_code:
            flight_number = airline_code + digits

    return flight_number


def calculate_time_left(flight: dict) -> int | None:
    """Calculate how much time (in minutes) is left until a flight arrives.

    - Returns 0 if the flight has already arrived (`actual_on` or `actual_in`).
    - Returns None if the flight has not departed (`actual_out` is None),
      or if no arrival estimates are available.
    - Otherwise, returns the number of minutes until arrival based on
      `estimated_in` (preferred) or `scheduled_in` (fallback).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduled_in = flight.get("scheduled_in")
    estimated_in = flight.get("estimated_in")

    if flight.get("actual_in") or flight.get("actual_on"):
        return 0

    elif not flight.get("actual_out"):
        return None

    # use estimated arrival if available
    elif estimated_in:
        estimated_arrival = parse_timestamp(estimated_in)
        if estimated_arrival:
            minutes = max(int((estimated_arrival - now).total_seconds() // 60), 0)
            return minutes if minutes >= 0 else None

    # fallback to scheduled arrival
    elif scheduled_in:
        scheduled_arrival = parse_timestamp(scheduled_in)
        if scheduled_arrival:
            minutes = max(int((scheduled_arrival - now).total_seconds() // 60), 0)
            return minutes if minutes >= 0 else None

    return None


def is_delayed(flight: dict) -> bool:
    """Return True if a flight is delayed"""
    departure_delay = flight.get("departure_delay")
    if departure_delay is not None:
        delay_minutes = departure_delay / 60.0
        if delay_minutes > 15:
            return True
    return False


def get_airline_details(flight_number: str) -> AirlineDetails:
    """Return airline details if they exist and are valid."""
    code = None

    # Try 2-letter IATA code first, then 3-letter ICAO code
    if flight_number[:2] in VALID_AIRLINE_CODES:
        code = flight_number[:2]
    elif flight_number[:3] in VALID_AIRLINE_CODES:
        code = flight_number[:3]

    airline_data = AIRLINE_CODE_TO_NAME_MAPPING.get(code, {}) if code else {}

    name = airline_data.get("name")
    name = name.title() if name else None
    color = airline_data.get("color")

    return AirlineDetails(
        code=code,
        name=name,
        color=color,
        icon=None,
    )
