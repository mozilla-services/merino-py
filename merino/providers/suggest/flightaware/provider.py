"""FlightAware Integration"""

import logging
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
)
from merino.providers.suggest.flightaware.backends.utils import (
    is_valid_flight_number_pattern,
)

logger = logging.getLogger(__name__)


class Provider(BaseProvider):
    """Suggestion provider for flight aware"""

    backend: FlightBackendProtocol
    metrics_client: aiodogstatsd.Client
    score: float

    def __init__(
        self,
        backend: FlightBackendProtocol,
        name: str,
        metrics_client: aiodogstatsd.Client,
        query_timeout_sec: float,
        score: float,
        enabled_by_default: bool = False,
    ):
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.url = HttpUrl("https://merino.services.mozilla.com/")
        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""
        # TODO

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    def normalize_query(self, query: str) -> str:
        """Remove trailing spaces from query and transform to uppercase"""
        return query.strip().upper()

    async def query(self, request: SuggestionRequest) -> list[BaseSuggestion]:
        """Retrieve flight suggestions"""
        try:
            temp_cache = set(
                ["3U1001", "AC701", "AA100", "UA3711", "AC432"]
            )  # to be replaced with in-memory cache

            if not is_valid_flight_number_pattern(request.query):
                return []
            else:
                query = request.query.replace(" ", "")

                if query in temp_cache:
                    result = await self.backend.fetch_flight_details(query)

                    if result:
                        flight_summaries: list[FlightSummary] = self.backend.get_flight_summaries(
                            result, query
                        )
                        return [self.build_suggestion(flight_summaries)]
            return []
        except Exception as e:
            logger.warning(f"Exception occurred for FlightAware provider: {e}")
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
