"""Protocol for flight aware provider backends."""

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, HttpUrl


class AirportDetails(BaseModel):
    """Details of origin/destination airport"""

    code: str
    city: str


class AirlineDetails(BaseModel):
    """Details of the operating airline for a flight"""

    code: str | None = None
    name: str | None = None
    color: str | None = None
    icon: HttpUrl | None = None


class FlightScheduleSegment(BaseModel):
    """Scheduled date and time details for a flight segment (e.g., departure or arrival)."""

    scheduled_time: datetime
    estimated_time: datetime | None


class FlightStatus(StrEnum):
    """Status of a specific flight instance"""

    SCHEDULED = "Scheduled"
    EN_ROUTE = "En Route"
    ARRIVED = "Arrived"
    CANCELLED = "Cancelled"
    DELAYED = "Delayed"
    UNKNOWN = "Unknown"


class FlightSummary(BaseModel):
    """Information about a specific flight instance"""

    flight_number: str
    destination: AirportDetails
    origin: AirportDetails
    departure: FlightScheduleSegment
    arrival: FlightScheduleSegment
    status: FlightStatus
    progress_percent: int = 0
    time_left_minutes: int | None = None
    delayed: bool
    url: HttpUrl
    airline: AirlineDetails


class GetFlightNumbersResultCode(Enum):
    """Enum to capture the result of getting flight numbers file."""

    SUCCESS = 0
    FAIL = 1


class FlightBackendProtocol(Protocol):
    """Protocol for a flight aware backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    def get_flight_summaries(self, flight_response: dict, query: str) -> list[FlightSummary]:
        """Return a prioritized list of summaries of a flight instance."""
        ...

    async def fetch_flight_details(self, flight_num: str) -> Any | None:
        """Fetch flight details by flight number through aeroAPI"""

    async def fetch_flight_numbers(
        self,
    ) -> tuple[GetFlightNumbersResultCode, list[str] | None]:
        """Fetch flight numbers file from GCS through the filemanager."""

    async def shutdown(self) -> None:  # pragma: no cover
        """Close http client connections."""
        ...
