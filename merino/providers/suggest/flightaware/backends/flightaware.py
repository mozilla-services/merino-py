"""A wrapper for Flight Aware API interactions."""

import asyncio
import datetime
import time
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
    derive_ttl_for_summaries,
    is_stale,
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
    cache: FlightCache

    def __init__(
        self,
        api_key: str,
        http_client: AsyncClient,
        ident_url: str,
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
        self.cache = FlightCache(cache)

    async def _refresh_flight_async(self, flight_num: str):
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
            result = response.json()

            summaries = self.get_flight_summaries(result, flight_num)
            if summaries:
                ttl_seconds = derive_ttl_for_summaries(summaries)
                await self.cache.set_flight(flight_num, summaries, ttl_seconds)
                logger.debug(f"Refreshed cache for {flight_num}")
        except Exception as e:
            logger.warning(f"Async refresh failed for {flight_num}: {e}")

    async def fetch_flight_details(self, flight_num: str) -> list[FlightSummary]:
        """Fetch flight summaries for a given flight number.

        Checks Redis cache first. On cache miss, fetches from AeroAPI,
        builds flight summaries, caches the result,
        and returns the summaries.
        """
        try:
            await self.cache.mark_accessed(flight_num)

            cached = await self.cache.get_flight(flight_num)

            if cached:
                summaries = [FlightSummary(**s) for s in cached.get("summaries", [])]
                return summaries

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

            result = response.json()

            summaries = self.get_flight_summaries(result, flight_num)
            logger.debug(f"FlightAware summaries for {flight_num}: {len(summaries)}")

            if summaries:
                is_scheduled = summaries[0].status == FlightStatus.SCHEDULED
                if is_scheduled:
                    dynamic_ttl = (
                        summaries[0].departure.estimated_time - now
                    )  # TODO verify time format here, also TTL?
                ttl_seconds = derive_ttl_for_summaries(summaries, dynamic_ttl)
                await self.cache.set_flight(flight_num, summaries, ttl_seconds)

            return summaries

        except HTTPStatusError as ex:
            logger.warning(
                f"Flightware request error for flight details: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            return []

    async def refresh_recent_flights(
        self,
        window_sec: int = 600,
        max_refresh: int = 100,
        min_age_sec: int = 300,
    ):
        """Periodically refresh recently accessed flights that may be stale.

        This background job runs on a fixed schedule to keep the FlightAware cache
        accurate around key flight transitions (e.g., scheduled → en route).
        It performs three main tasks each cycle:

        1. Prune old access records — removes entries from the
            `flight_last_access` sorted set that haven't been searched recently
            (older than `older_than_sec`, defined in `prune_old_access_records()`).

        2. Select recent flights — scans the remaining records and selects
            flights that were searched within the last `window_sec` seconds.

        3. Refresh stale data — for each selected flight:
                • If the cached data is considered stale
                (e.g., departure time has passed), or
                • If the flight is currently en route,
            the backend triggers a background refresh from the AeroAPI
            to update its cache entry.

        Args:
            window_sec:
                Lookback window (in seconds) to identify flights that have been
                accessed recently and are eligible for refresh. Defaults to 10 minutes.

            max_refresh:
                Maximum number of flights to refresh in a single cycle to avoid
                exceeding API quotas. Defaults to 100.

        Notes:
            - Cached flights that are neither soft-stale nor en-route are skipped.
        """
        try:
            # prune stale access records first
            removed = await self.cache.prune_old_access_records(older_than_sec=1800)
            if removed:
                logger.debug(f"Pruned {removed} old records from flight_last_access")
            now = time.time()
            cutoff = now - window_sec

            # get flights accessed in the last `window_sec`
            recent_keys = await self.cache.redis.zrangebyscore(
                "flight_last_access", min=cutoff, max=now
            )
            if not recent_keys:
                logger.debug("No recently accessed flights found for background refresh.")
                return

            refreshed = 0
            for key in recent_keys:
                if refreshed >= max_refresh:
                    logger.debug("Reached max refresh limit for this cycle.")
                    break

                flight_num = key.decode().split(":")[-1]
                cached = await self.cache.get_flight(flight_num)
                if not cached:
                    continue  # should we fetch again here?

                fetched_at_str = cached.get("fetched_at")
                if not fetched_at_str:
                    continue

                fetched_at = datetime.datetime.fromisoformat(fetched_at_str)
                age_sec = (
                    datetime.datetime.now(datetime.timezone.utc) - fetched_at
                ).total_seconds()
                if age_sec < min_age_sec:
                    # skip flights updated too recently
                    continue

                summaries = [FlightSummary(**s) for s in cached.get("summaries", [])]
                statuses = {s.status for s in summaries}
                is_enroute = FlightStatus.EN_ROUTE in statuses

                # only refresh if the flight is stale or en-route
                if is_stale(summaries) or is_enroute:
                    logger.debug(f"Background refresh triggered for {flight_num}")
                    asyncio.create_task(self._refresh_flight_async(flight_num))
                    refreshed += 1

            logger.info(
                f"Flightaware background refresh cycle completed. Refreshed {refreshed} flights."
            )

        except Exception as e:
            logger.warning(f"Flightaware background refresh job failed: {e}")

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
