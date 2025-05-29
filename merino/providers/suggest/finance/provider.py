"""Finance integration."""

import asyncio
import logging
from typing import Any

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl


# from merino.governance.circuitbreakers import WeatherCircuitBreaker
# from merino.middleware.geolocation import Location
from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.finance.backends.protocol import FinanceBackend

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for finance suggestions."""

    # TODO


class Provider(BaseProvider):
    """Suggestion provider for finance."""

    backend: FinanceBackend
    metrics_client: aiodogstatsd.Client
    score: float
    dummy_url: HttpUrl
    cron_task: asyncio.Task
    cron_interval_sec: float

    def __init__(
        self,
        backend: FinanceBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default

        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        # TODO

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if srequest.query and not srequest.request_type:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `request_type` is missing",
            )

    # TODO: circuit breaker
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions.

        # TODO
        All the `PolygonError` errors, raised from the backend, are intentionally
        unhandled in this function to drive the circuit breaker. Those exceptions will
        eventually be propagated to the provider consumer (i.e. the API handler) and be
        handled there.
        """
        # TODO: pull useful variables from `srequest` object
        # TODO: add a 'FinanceContext dataclass model'
        try:
            with self.metrics_client.timeit(f"providers.{self.name}.query.backend.get"):
                # TODO: add backend function call
                print("TODO: add backend function call")
        except Exception:
            # TODO
            return []
        # TODO
        return []

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
