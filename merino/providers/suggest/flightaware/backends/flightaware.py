"""A wrapper for Flight Aware API interactions."""

import datetime
from typing import Any
from httpx import AsyncClient, HTTPStatusError

import logging
from merino.configs import settings
from merino.providers.suggest.flightaware.backends.filemanager import (
    FlightawareFilemanager,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    FlightBackendProtocol,
    FlightSummary,
    GetFlightNumbersResultCode,
)
from merino.providers.suggest.flightaware.backends.utils import (
    build_flight_summary,
    pick_best_flights,
)

logger = logging.getLogger(__name__)

GCS_BLOB_NAME = "flight_numbers_latest.json"


class FlightAwareBackend(FlightBackendProtocol):
    """Backend that connects to the Flight Aware API."""

    api_key: str
    http_client: AsyncClient
    ident_url: str
    filemanager: FlightawareFilemanager

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
        self.filemanager = FlightawareFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )

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

    async def fetch_flight_numbers(
        self,
    ) -> tuple[GetFlightNumbersResultCode, list[str] | None]:
        """Fetch flight numbers file from GCS through the filemanager."""
        try:
            return await self.filemanager.get_file()
        except Exception as e:
            logger.warning(f"Failed to fetch flight numbers from GCS: {e}")
            return GetFlightNumbersResultCode.FAIL, None

    async def shutdown(self) -> None:
        """Close http client connections."""
        await self.http_client.aclose()
