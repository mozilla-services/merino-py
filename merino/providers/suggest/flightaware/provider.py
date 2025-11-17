"""FlightAware Integration"""

import asyncio
import logging
import time
import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl
from merino.providers.suggest.base import (
    BaseProvider,
    BaseSuggestion,
    SuggestionRequest,
)
from merino.providers.suggest.custom_details import CustomDetails, FlightAwareDetails
from merino.providers.suggest.flightaware.backends.protocol import (
    FlightBackendProtocol,
    FlightSummary,
    GetFlightNumbersResultCode,
)
from merino.providers.suggest.flightaware.backends.utils import (
    get_flight_number_from_query_if_valid,
)
from merino.utils import cron
from merino.configs import settings

logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Suggestion provider for flight aware"""

    backend: FlightBackendProtocol
    metrics_client: aiodogstatsd.Client
    score: float
    flight_numbers: set[str]
    resync_interval_sec: int
    cron_interval_sec: int

    def __init__(
        self,
        backend: FlightBackendProtocol,
        name: str,
        metrics_client: aiodogstatsd.Client,
        query_timeout_sec: float,
        score: float,
        resync_interval_sec: int,
        cron_interval_sec: int,
        enabled_by_default: bool = False,
    ):
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.last_fetch_at = 0.0
        self.flight_numbers = set()
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.data_fetched_event = asyncio.Event()
        super().__init__()

    async def initialize(self) -> None:
        """Initialize flight aware provider."""
        if settings.image_gcs.gcs_enabled:
            await self._fetch_data()

            cron_job = cron.Job(
                name="resync_flightaware",
                interval=self.cron_interval_sec,
                condition=self._should_fetch,
                task=self._fetch_data,
            )
            self.cron_task = asyncio.create_task(cron_job())

    async def _fetch_data(self) -> None:
        """Cron fetch method to re-run after set interval.
        Does not set flight_numbers if non-success code passed with None.
        """
        try:
            result_code, data = await self.backend.fetch_flight_numbers()

            match GetFlightNumbersResultCode(result_code):
                case GetFlightNumbersResultCode.SUCCESS if data is not None:
                    self.flight_numbers = set(data)

                    self.last_fetch_at = time.time()
                    logger.info("Successfully fetched and set flight numbers from backend.")

                case GetFlightNumbersResultCode.FAIL:
                    logger.error("Failed to fetch data from flightaware backend.")
                    return None
        except Exception as err:
            logger.error(f"Failed to fetch data from flightaware backend: {err}")

        finally:
            self.data_fetched_event.set()

    def _should_fetch(self) -> bool:
        """Determine if we should fetch new data based on time elapsed."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    def normalize_query(self, query: str) -> str:
        """Remove trailing spaces from query and convert to lowercase"""
        return query.strip()

    async def query(self, request: SuggestionRequest) -> list[BaseSuggestion]:
        """Retrieve flight suggestions"""
        try:
            flight_number = get_flight_number_from_query_if_valid(request.query)

            if flight_number is None:
                return []
            if flight_number in self.flight_numbers:
                self.metrics_client.increment(
                    f"providers.{self.name}.flight_no_pattern.match_count"
                )

                result = await self.backend.fetch_flight_details(flight_number)

                if result:
                    return [self.build_suggestion(result)]
            return []
        except Exception as e:
            logger.warning(f"Exception occurred for FlightAware provider: {e}")
            self.metrics_client.increment(f"providers.{self.name}.query.exception")
            return []

    def build_suggestion(self, relevant_flights: list[FlightSummary]) -> BaseSuggestion:
        """Build a base suggestion with custom flight details"""
        return BaseSuggestion(
            title="Flight Suggestion",
            url=HttpUrl(self.url),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            custom_details=CustomDetails(flightaware=FlightAwareDetails(values=relevant_flights)),
        )

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
