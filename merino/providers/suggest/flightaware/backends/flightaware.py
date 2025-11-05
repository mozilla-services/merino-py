"""A wrapper for Flight Aware API interactions."""

import datetime
from typing import Any
import aiodogstatsd
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
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        ident_url: str,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        """Initialize the flight aware backend."""
        self.api_key = api_key
        self.http_client = http_client
        self.ident_url = ident_url
        self.filemanager = FlightawareFilemanager(
            gcs_bucket_path=settings.image_gcs.gcs_bucket,
            blob_name=GCS_BLOB_NAME,
        )
        self.metrics_client = metrics_client

    async def fetch_flight_details(self, flight_num: str) -> Any | None:
        """Fetch flight details through aeroAPI"""
        try:
            metric_base = "flightaware.request.summary.get"
            self.metrics_client.increment(f"{metric_base}.count")
            header = {
                "x-apikey": self.api_key,
                "Accept": "application/json",
            }

            now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            start = (now - datetime.timedelta(hours=20)).isoformat().replace("+00:00", "Z")
            end = (now + datetime.timedelta(hours=28)).isoformat().replace("+00:00", "Z")

            formatted_url = self.ident_url.format(ident=flight_num, start=start, end=end)

            with self.metrics_client.timeit(f"{metric_base}.latency"):
                response = await self.http_client.get(formatted_url, headers=header)
                response.raise_for_status()
                self.metrics_client.increment(
                    f"{metric_base}.status", tags={"status_code": response.status_code}
                )
            return response.json()

        except HTTPStatusError as ex:
            status_code = ex.response.status_code
            self.metrics_client.increment(
                f"{metric_base}.status", tags={"status_code": status_code}
            )
            logger.warning(
                f"Flightware request error for flight details for {flight_num}: {status_code} {ex.response.reason_phrase}"
            )
            return None

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
