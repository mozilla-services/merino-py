"""A wrapper for Flight Aware API interactions."""

import datetime
import aiodogstatsd
from httpx import AsyncClient, HTTPStatusError

import logging
from merino.cache.protocol import CacheAdapter
from merino.configs import settings
from merino.providers.suggest.flightaware.backends.cache import FlightCache
from merino.providers.suggest.flightaware.backends.filemanager import (
    FlightawareFilemanager,
)
from merino.providers.suggest.flightaware.backends.protocol import (
    FlightBackendProtocol,
    FlightStatus,
    FlightSummary,
    GetFlightNumbersResultCode,
)
from merino.providers.suggest.flightaware.backends.utils import (
    build_flight_summary,
    compute_enroute_progress,
    derive_ttl_for_summaries,
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
    cache: FlightCache

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        ident_url: str,
        metrics_client: aiodogstatsd.Client,
        cache: CacheAdapter,
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
        self.cache = FlightCache(cache)

    async def fetch_flight_details(self, flight_num: str) -> list[FlightSummary] | None:
        """Fetch flight summaries for a given flight number.

        Checks Redis cache first. On cache miss, fetches from AeroAPI,
        builds flight summaries, caches the result,
        and returns the summaries.
        """
        try:
            metric_base = "flightaware.request.summary"
            self.metrics_client.increment(f"{metric_base}.get.count")

            cached = await self.cache.get_flight(flight_num)

            if cached:
                self.metrics_client.increment(f"{metric_base}.cache.hit")
                summaries = cached.summaries

                if summaries:
                    # update progress/time left for the first flight if enroute
                    first = summaries[0]
                    if first.status == FlightStatus.EN_ROUTE:
                        progress, time_left = compute_enroute_progress(first)
                        first.progress_percent = progress
                        first.time_left_minutes = time_left
                        summaries[0] = first

                return summaries

            self.metrics_client.increment(f"{metric_base}.cache.miss")
            header = {
                "x-apikey": self.api_key,
                "Accept": "application/json",
            }

            now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            start = (now - datetime.timedelta(hours=20)).isoformat().replace("+00:00", "Z")
            end = (now + datetime.timedelta(hours=28)).isoformat().replace("+00:00", "Z")

            formatted_url = self.ident_url.format(ident=flight_num, start=start, end=end)

            with self.metrics_client.timeit(f"{metric_base}.get.latency"):
                response = await self.http_client.get(formatted_url, headers=header)
                response.raise_for_status()
                self.metrics_client.increment(
                    f"{metric_base}.get.status",
                    tags={"status_code": response.status_code},
                )
            summaries = self.get_flight_summaries(response.json(), flight_num)

            if summaries:
                ttl = derive_ttl_for_summaries(summaries)
                await self.cache.set_flight(flight_num, summaries, ttl)

                return summaries
            return []

        except HTTPStatusError as ex:
            status_code = ex.response.status_code
            self.metrics_client.increment(
                f"{metric_base}.get.status", tags={"status_code": status_code}
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
