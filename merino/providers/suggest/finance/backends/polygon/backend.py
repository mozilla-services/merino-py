"""A wrapper for Polygon API interactions."""

import aiodogstatsd
from httpx import AsyncClient, Response
from pydantic import BaseModel

from merino.cache.protocol import CacheAdapter
from merino.providers.suggest.finance.backends.polygon.utils import (
    FinanceEntityType,
    TickerSnapshot,
    extract_ticker_snapshot,
)

# Export all the classes from this module
__all__ = [
    "StockPrice",
    "IndexPrice",
    "PolygonBackend",
]


class StockPrice(BaseModel):
    """Model for a Stock"""

    type: FinanceEntityType = FinanceEntityType.STOCK
    ticker_symbol: str
    price: float


class IndexPrice(BaseModel):
    """Model for a Index"""

    type: FinanceEntityType = FinanceEntityType.INDEX
    ticker_symbol: str
    price: float


class PolygonBackend:
    """Backend that connects to the Polygon API."""

    api_key: str
    cache: CacheAdapter
    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    metrics_sample_rate: float

    url_param_api_key: str
    url_ticker_last_quote: str
    url_index_daily_summary: str

    def __init__(
        self,
        api_key: str,
        url_param_api_key: str,
        url_ticker_last_quote: str,
        url_index_daily_summary: str,
        url_single_ticker_snapshot: str,
        cache: CacheAdapter,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        metrics_sample_rate: float,
    ) -> None:
        """Initialize the Polygon backend.

        Raises:
            ValueError: If API key or URL variables are None or empty.
        """
        required_params = {
            "api_key": api_key,
            "url_ticker_last_quote": url_ticker_last_quote,
            "url_index_daily_summary": url_index_daily_summary,
        }

        # validate required parameters
        missing = [name for name, value in required_params.items() if not value]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        self.api_key = api_key
        self.cache = cache
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.metrics_sample_rate = metrics_sample_rate
        self.url_param_api_key = url_param_api_key
        self.url_ticker_last_quote = url_ticker_last_quote
        self.url_index_daily_summary = url_index_daily_summary
        self.url_single_ticker_snapshot = url_single_ticker_snapshot

    # WIP
    # async def get_finance_report(self, finance_context: FinanceContext) -> FinanceReport:
    #     """Get the finance report for stock ticker"""
    #     ticker = finance_context.ticker_symbol
    #     stock_price = await self.get_ticker_snapshot(ticker)
    #     finance_report = FinanceReport(
    #         entity_type=finance_context.entity_type, ticker_symbol=ticker, price=stock_price.price
    #     )

    #     return finance_report

    async def get_ticker_snapshot(self, ticker: str) -> TickerSnapshot:
        """Get the stock price for the ticker"""
        params = {self.url_param_api_key: self.api_key}

        response: Response = await self.http_client.get(
            self.url_single_ticker_snapshot.format(ticker=ticker), params=params
        )
        response.raise_for_status()

        # build and return response as a ticker snapshot
        return extract_ticker_snapshot(response.json())

    async def get_index_price(self, ticker_symbol: str, date: str) -> IndexPrice:
        """Get the index price for the ticker"""
        params = {
            self.url_param_api_key: self.url_param_api_key,
            "indices_ticker": ticker_symbol,
            "date": date,  # TODO fix type
        }
        response: Response = await self.http_client.get(
            self.url_index_daily_summary, params=params
        )
        response.raise_for_status()

        index_data = response.json().results

        # build and return response
        return IndexPrice(ticker_symbol=index_data.symbol, price=index_data.open)

    async def shutdown(self) -> None:
        """Close http client and cache connections."""
        await self.http_client.aclose()
        await self.cache.close()
