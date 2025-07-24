"""Finance integration."""

import logging
from typing import Any

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.finance.backends.polygon.utils import TickerSnapshot, TickerSymbol
from merino.providers.suggest.finance.backends.protocol import FinanceBackend

logger = logging.getLogger(__name__)


class FinanceSuggestion(BaseSuggestion):
    """Model for finance suggestions."""

    # TODO will expand / change
    ticker_snapshot: TickerSnapshot


class Provider(BaseProvider):
    """Suggestion provider for finance."""

    backend: FinanceBackend
    metrics_client: aiodogstatsd.Client
    score: float
    dummy_url: HttpUrl

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
        self.dummy_url = HttpUrl("http://www.dummy.com")

        super().__init__(**kwargs)

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

    # TODO: circuit breaker
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions.

        All the `PolygonError` errors, raised from the backend, are intentionally
        unhandled in this function to drive the circuit breaker. Those exceptions will
        eventually be propagated to the provider consumer (i.e. the API handler) and be
        handled there.
        """
        try:
            # build the stock enum from query param q and do a snapshot req
            ticker = TickerSymbol(srequest.query)
            # possible logic to branch search and snapshot req

            snapshot = await self.backend.get_ticker_snapshot(ticker)
            finance_suggestion: FinanceSuggestion = self.build_suggestion(snapshot)
            return [finance_suggestion]

        # TODO: Replace for circuit breakers
        except Exception as e:
            logger.warning(f"Exception occurred for Polygon provider: {e}")
            return []

    def build_suggestion(self, data: TickerSnapshot) -> FinanceSuggestion:
        """Build a FinanceSuggestion from a TickerSnapshot"""
        return FinanceSuggestion(
            title="Stock suggestion",
            url=HttpUrl(self.dummy_url),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            ticker_snapshot=data,
        )

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
