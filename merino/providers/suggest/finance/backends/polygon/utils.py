"""Utilities for the Polygon backend"""

import logging
from typing import Any

from pydantic import HttpUrl
from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary
from merino.providers.suggest.finance.backends.polygon.stock_ticker_company_mapping import (
    ALL_STOCK_TICKER_COMPANY_MAPPING,
)
from merino.providers.suggest.finance.backends.polygon.etf_ticker_company_mapping import (
    ALL_ETF_TICKER_COMPANY_MAPPING,
)
from merino.providers.suggest.finance.backends.polygon.keyword_ticker_mapping import (
    KEYWORD_TO_STOCK_TICKER_MAPPING,
    KEYWORD_TO_ETF_TICKER_MAPPING,
)

logger = logging.getLogger(__name__)


def lookup_ticker_company(ticker: str) -> str:
    """Get the ticker company for ticker symbol. Stock or ETF."""
    return ALL_STOCK_TICKER_COMPANY_MAPPING[ticker.upper()]["company"]


def lookup_ticker_exchange(ticker: str) -> str:
    """Get the ticker exchange for ticker symbol. Stock or ETF."""
    return ALL_STOCK_TICKER_COMPANY_MAPPING[ticker.upper()]["exchange"]


def get_tickers_for_query(keyword: str) -> list[str] | None:
    """Validate and return a list of tickers (1 to 3) or None."""
    if keyword.upper() in ALL_STOCK_TICKER_COMPANY_MAPPING:
        return [keyword.upper()]
    if keyword.upper() in ALL_ETF_TICKER_COMPANY_MAPPING:
        return [keyword.upper()]
    if ticker := KEYWORD_TO_STOCK_TICKER_MAPPING.get(keyword):
        return [ticker]
    if tickers := KEYWORD_TO_ETF_TICKER_MAPPING.get(keyword):
        return list(tickers)

    return None


def extract_snapshot_if_valid(data: dict[str, Any] | None) -> TickerSnapshot | None:
    """Extract the TickerSnapshot from the nested JSON response, if it has the valid json structure."""
    match data:
        case None:
            return None
        case {
            "ticker": {
                "ticker": str(ticker),
                "todaysChangePerc": float(todays_change),
                "lastTrade": {"p": float(last_price)},
            }
        }:
            return TickerSnapshot(
                ticker=ticker,
                todays_change_perc=f"{todays_change:.2f}",
                last_price=f"{last_price:.2f}",
            )
        case _:
            logger.warning(f"Polygon invalid ticker snapshot json response: {data}")
            return None


def build_ticker_summary(snapshot: TickerSnapshot, image_url: HttpUrl | None) -> TickerSummary:
    """Build a ticker summary for a finance suggestion response."""
    ticker = snapshot.ticker
    company = lookup_ticker_company(ticker)
    exchange = lookup_ticker_exchange(ticker)
    serp_query = f"{ticker} stock"
    last_price = f"${snapshot.last_price} USD"
    todays_change_perc = snapshot.todays_change_perc

    return TickerSummary(
        ticker=ticker,
        name=company,
        last_price=last_price,
        todays_change_perc=todays_change_perc,
        query=serp_query,
        image_url=image_url,
        exchange=exchange,
    )
