"""Protocol for flight aware provider backends."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, HttpUrl


class AirportDetails(BaseModel):
    """Details of origin/destination airport"""

    code: str
    city: str


class FlightScheduleSegment(BaseModel):
    """Scheduled date and time details for a flight segment (e.g., departure or arrival)."""

    scheduled_time: datetime
    estimated_time: datetime


# TODO these will be properly deducted in DISCO-3736
class FlightStatus(StrEnum):
    """Status of a specific flight instance"""

    SCHEDULED = "Scheduled"
    EN_ROUTE = "En Route"
    ARRIVED = "Arrived"
    CANCELLED = "Cancelled"
    DELAYED = "Delayed"


class FlightSummary(BaseModel):
    """Information about a specific flight instance"""

    flight_number: str
    destination: AirportDetails
    origin: AirportDetails
    departure: FlightScheduleSegment
    arrival: FlightScheduleSegment
    status: str  # TODO string for now, will replace with enum in DISCO-3736
    progress_percent: int | None
    # TODO these will be properly deducted in DISCO-3736
    # delayed_until: datetime | None
    # time_left_minutes: int | None
    url: HttpUrl


class FlightBackendProtocol(Protocol):
    """Protocol for a flight aware backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    def get_flight_summaries(self, flight_response: Any, query: str) -> list[FlightSummary]:
        """Return a prioritized list of summaries of a flight instance."""
        ...

    async def fetch_flight_details(self, flight_num: str) -> Any | None:
        """Fetch flight details by flight number through aeroAPI"""

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
