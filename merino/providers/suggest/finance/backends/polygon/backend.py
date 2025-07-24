"""A wrapper for Polygon API interactions."""

import aiodogstatsd
from httpx import AsyncClient, Response
from typing import Any

from merino.cache.protocol import CacheAdapter
from merino.providers.suggest.finance.backends.polygon.utils import (
    TickerSnapshot,
    extract_ticker_snapshot,
    build_ticker_summary,
)

# Export all the classes from this module
__all__ = [
    "PolygonBackend",
]


class PolygonBackend:
    """Backend that connects to the Polygon API."""

    api_key: str
    cache: CacheAdapter
    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    metrics_sample_rate: float

    url_param_api_key: str
    url_single_ticker_snapshot: str

    def __init__(
        self,
        api_key: str,
        url_param_api_key: str,
        url_single_ticker_snapshot: str,
        cache: CacheAdapter,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        metrics_sample_rate: float,
    ) -> None:
        """Initialize the Polygon backend."""
        self.api_key = api_key
        self.cache = cache
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.metrics_sample_rate = metrics_sample_rate
        self.url_param_api_key = url_param_api_key
        self.url_single_ticker_snapshot = url_single_ticker_snapshot

    async def get_ticker_summary(self, ticker: str) -> dict[str, str]:
        """TODO"""
        snapshot: TickerSnapshot = extract_ticker_snapshot(
            await self.fetch_ticker_snapshot(ticker)
        )

        return build_ticker_summary(ticker=ticker, snapshot=snapshot)

    async def fetch_ticker_snapshot(self, ticker: str) -> dict[str, Any]:
        """Make a request and fetch the snapshot for this single ticker."""
        params = {self.url_param_api_key: self.api_key}

        response: Response = await self.http_client.get(
            self.url_single_ticker_snapshot.format(ticker=ticker), params=params
        )
        response.raise_for_status()

        return response.json()

    async def shutdown(self) -> None:
        """Close http client and cache connections."""
        await self.http_client.aclose()
        await self.cache.close()
