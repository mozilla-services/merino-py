"""Finance integration."""

import logging

import aiodogstatsd
from fastapi import HTTPException
from pydantic import HttpUrl

from merino.providers.suggest.base import BaseProvider, BaseSuggestion, SuggestionRequest
from merino.providers.suggest.finance.backends.polygon.utils import TickerSnapshot
from merino.providers.suggest.finance.backends.protocol import FinanceBackend
from merino.providers.suggest.finance.backends.polygon.utils import is_valid_ticker

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
    url: HttpUrl

    def __init__(
        self,
        backend: FinanceBackend,
        metrics_client: aiodogstatsd.Client,
        score: float,
        name: str,
        query_timeout_sec: float,
        url: HttpUrl,
        enabled_by_default: bool = False,
    ) -> None:
        self.backend = backend
        self.metrics_client = metrics_client
        self.score = score
        self._name = name
        self._query_timeout_sec = query_timeout_sec
        self._enabled_by_default = enabled_by_default
        self.url = url

        super().__init__()

    async def initialize(self) -> None:
        """Initialize the provider."""

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate the suggestion request."""
        if not srequest.query:
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: `q` is missing",
            )

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide finance suggestions."""
        # get a stock snapshot if the query param contains a supported ticker else do a search for that ticker
        try:
            if not is_valid_ticker(srequest.query):
                return []
            else:
                # Normalize the ticker to upper case since all downstream methods rely on it being upper.
                ticker = srequest.query.upper()
                # TODO type
                # ticker_summary= await self.backend.get_ticker_summary(ticker)
                # finance_suggestion: FinanceSuggestion = self.build_suggestion(ticker_summary)
                await self.backend.get_ticker_summary(ticker)
                return []
                # return [finance_suggestion]

        except Exception as e:
            logger.warning(f"Exception occurred for Polygon provider: {e}")
            return []

    # TODO refactor to new shape
    def build_suggestion(self, data: TickerSnapshot) -> FinanceSuggestion:
        """Build a FinanceSuggestion from a TickerSnapshot"""
        return FinanceSuggestion(
            title="Stock suggestion",
            url=HttpUrl(self.url),
            provider=self.name,
            is_sponsored=False,
            score=self.score,
            ticker_snapshot=data,
        )

    async def shutdown(self) -> None:
        """Shut down the provider."""
        await self.backend.shutdown()
