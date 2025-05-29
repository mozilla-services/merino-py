"""A wrapper for Polygon API interactions."""

import aiodogstatsd
from httpx import AsyncClient, Response
from pydantic import BaseModel

from merino.cache.protocol import CacheAdapter


class StockPrice(BaseModel):
    """TODO"""

    ticker_symbol: str
    price: float


class IndexPrice(BaseModel):
    """TODO"""

    ticker_symbol: str
    price: float


class PolygonBackend:
    """Backend that connects to the Polygon API."""

    api_key: str
    cache: CacheAdapter
    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    metrics_sample_rate: float

    def __init__(
        self,
        url_param_api_key: str,
        url_ticker_last_quote: str,
        url_index_daily_summary: str,
        cache: CacheAdapter,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        metrics_sample_rate: float,
    ) -> None:
        """TODO"""
        required_params = {
            "Polygon API key": url_param_api_key,
            "url_ticker_last_quote": url_ticker_last_quote,
            "url_index_daily_summary": url_index_daily_summary,
        }

        # validate required parameters
        missing = [name for name, value in required_params.items() if not value]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        self.url_param_api_key = url_param_api_key
        self.cache = cache
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.metrics_sample_rate = metrics_sample_rate
        self.url_ticker_last_quote = url_ticker_last_quote
        self.url_index_daily_summary = url_index_daily_summary

    async def get_stock_price(self, ticker_symbol: str) -> StockPrice:
        """TODO"""
        params = {
            self.url_param_api_key: self.url_param_api_key,
            "stock_ticker": ticker_symbol,
        }
        response: Response = await self.http_client.get(self.url_ticker_last_quote, params=params)
        response.raise_for_status()

        # TODO add type for stock_data
        stock_data = response.json().results

        # build and return response
        return StockPrice(ticker_symbol=stock_data.T, price=stock_data.P)

    async def get_index_price(self, ticker_symbol: str, date: str) -> IndexPrice:
        """TODO"""
        params = {
            self.url_param_api_key: self.url_param_api_key,
            "indices_ticker": ticker_symbol,
            "date": date,  # TODO fix type
        }
        response: Response = await self.http_client.get(
            self.url_index_daily_summary, params=params
        )
        response.raise_for_status()

        # TODO add type for stock_data
        index_data = response.json().results

        # build and return response
        return IndexPrice(ticker_symbol=index_data.symbol, price=index_data.open)
