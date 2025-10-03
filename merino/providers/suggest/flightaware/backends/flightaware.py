"""A wrapper for Flight Aware API interactions."""

import datetime
from typing import Any
from httpx import AsyncClient, HTTPStatusError

import logging
from merino.providers.suggest.flightaware.backends.protocol import (
    FlightBackendProtocol,
    FlightSummary,
)
from merino.providers.suggest.flightaware.backends.utils import (
    build_flight_summary,
    pick_best_flights,
)

logger = logging.getLogger(__name__)


class FlightAwareBackend(FlightBackendProtocol):
    """Backend that connects to the Flight Aware API."""

    api_key: str
    http_client: AsyncClient
    ident_url: str

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        ident_url: str,
    ) -> None:
        """Initialize the flight aware backend."""
        self.api_key = api_key
        self.http_client = http_client
        self.ident_url = ident_url

    async def fetch_flight_details(self, flight_num: str) -> Any | None:
        """Fetch flight details through aeroAPI"""
        try:
            header = {
                "x-apikey": self.api_key,
                "Accept": "application/json",
            }

            now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            start = (now - datetime.timedelta(hours=20)).isoformat().replace("+00:00", "Z")
            end = (now + datetime.timedelta(hours=28)).isoformat().replace("+00:00", "Z")

            formatted_url = self.ident_url.format(ident=flight_num, start=start, end=end)

            response = await self.http_client.get(formatted_url, headers=header)
            response.raise_for_status()

        except HTTPStatusError as ex:
            logger.warning(
                f"Flightware request error for flight details: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            return None

        return response.json()

    def get_flight_summaries(
        self, flight_response: dict | None, query: str
    ) -> list[FlightSummary]:
        """Return a prioritized list of summaries of a flight instance."""
        if flight_response is None:
            return []

        flights = flight_response["flights"] or []
        prioritized_flights = pick_best_flights(flights)

        return [
            summary
            for flight in prioritized_flights
            if (summary := build_flight_summary(flight, query)) is not None
        ]

    async def shutdown(self) -> None:
        """Shutdown any persistent connections. Currently a no-op."""
        pass
