"""Finance integration."""

import asyncio
import logging
from typing import Any

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.finance.backends.polygon.utils import FinanceEntityType, TickerSymbol
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceContext,
    FinanceReport,
)

logger = logging.getLogger(__name__)


class FinanceSuggestion(BaseSuggestion):
    """Model for finance suggestions."""

    # TODO will expand / change
    finance_report: FinanceReport


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

        All the `PolygonError` errors, raised from the backend, are intentionally
        unhandled in this function to drive the circuit breaker. Those exceptions will
        eventually be propagated to the provider consumer (i.e. the API handler) and be
        handled there.
        """
        try:
            if not srequest.request_type == "stock":
                return []

            # test for now
            finance_context = FinanceContext(
                entity_type=FinanceEntityType.STOCK,
                ticker_symbol=TickerSymbol.AAPL,
                request_type="price",
            )

            finance_report = await self.backend.get_finance_report(finance_context)
            finance_suggestion: FinanceSuggestion = self.build_suggestion(finance_report)
            return [finance_suggestion]

        except Exception:
            # TODO
            return []

    def build_suggestion(self, data: FinanceReport) -> FinanceSuggestion:
        """Build a FinanceSuggestion from a FinanceReport"""
        return FinanceSuggestion(
            title="Stock suggestion",
            url=HttpUrl("www.test.com"),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            finance_report=data,
        )

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
