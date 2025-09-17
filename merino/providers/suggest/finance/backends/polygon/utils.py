"""Utilities for the Polygon backend"""

import logging
from typing import Any

from pydantic import HttpUrl
from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary
from merino.providers.suggest.finance.backends.polygon.stock_ticker_company_mapping import (
    ALL_STOCK_TICKER_COMPANY_MAPPING,
    STOCK_TICKER_MATCH_BLOCKLIST,
)
from merino.providers.suggest.finance.backends.polygon.etf_ticker_company_mapping import (
    ALL_ETF_TICKER_COMPANY_MAPPING,
    ETF_TICKER_MATCH_BLOCKLIST,
)
from merino.providers.suggest.finance.backends.polygon.keyword_ticker_mapping import (
    KEYWORD_TO_STOCK_TICKER_MAPPING,
    KEYWORD_TO_ETF_TICKER_MAPPING,
)

logger = logging.getLogger(__name__)

ALL_TICKER_COMPANY_MAPPING: dict[str, dict] = {
    **ALL_STOCK_TICKER_COMPANY_MAPPING,
    **ALL_ETF_TICKER_COMPANY_MAPPING,
}


def lookup_ticker_company(ticker: str) -> str:
    """Get the ticker company for a stock or ETF ticker symbol."""
    return str(ALL_TICKER_COMPANY_MAPPING[ticker]["company"])


def lookup_ticker_exchange(ticker: str) -> str:
    """Get the ticker exchange for ticker symbol. Stock or ETF."""
    return str(ALL_TICKER_COMPANY_MAPPING[ticker]["exchange"])


def get_tickers_for_query(keyword: str) -> list[str] | None:
    """Validate and return a list of tickers (1 to 3) or None."""
    keyword_upper = keyword.upper()

    if (
        keyword_upper in STOCK_TICKER_MATCH_BLOCKLIST
        or keyword_upper in ETF_TICKER_MATCH_BLOCKLIST
    ):
        return None
    if keyword_upper in ALL_STOCK_TICKER_COMPANY_MAPPING:
        return [keyword_upper]
    if keyword_upper in ALL_ETF_TICKER_COMPANY_MAPPING:
        return [keyword_upper]
    if ticker := KEYWORD_TO_STOCK_TICKER_MAPPING.get(keyword):
        return [ticker]
    if tickers := KEYWORD_TO_ETF_TICKER_MAPPING.get(keyword):
        return tickers

    return None


def extract_snapshot_if_valid(data: dict[str, Any] | None) -> TickerSnapshot | None:
    """Extract the TickerSnapshot from the nested JSON response, if it has the valid json structure."""
    if data is None:
        return None

    try:
        result = data["results"][0]
        ticker = result["ticker"]
        market_status = result["market_status"]

        # Default price and change percent values based on if market status is open.
        # Overriden below if market status changes.
        price = result["session"]["price"]
        change_percent = result["session"]["change_percent"]

        if market_status == "early_trading":
            price = result["session"]["previous_close"]
            change_percent = result["session"]["early_trading_change_percent"]

        if market_status == "closed" or market_status == "late_trading":
            price = result["session"]["close"]
            change_percent = result["session"]["regular_trading_change_percent"]

        if not isinstance(change_percent, float) or not isinstance(price, float):
            logger.warning(f"Polygon snapshot response json has incorrect data types: {data}")
            return None

        # Formatting the values to two decimal places and string type.
        todays_change_percent = (
            f"+{change_percent:.2f}" if change_percent > 0 else f"{change_percent:.2f}"
        )
        last_trade_price = f"{price:.2f}"

        return TickerSnapshot(
            ticker=ticker,
            todays_change_percent=todays_change_percent,
            last_trade_price=last_trade_price,
        )
    except (KeyError, IndexError, TypeError):
        logger.warning(f"Polygon snapshot response json has incorrect shape: {data}")
        return None


def build_ticker_summary(snapshot: TickerSnapshot, image_url: HttpUrl | None) -> TickerSummary:
    """Build a ticker summary for a finance suggestion response."""
    ticker = snapshot.ticker
    company = lookup_ticker_company(ticker)
    exchange = lookup_ticker_exchange(ticker)
    serp_query = f"{ticker} stock"
    last_price = f"${snapshot.last_trade_price} USD"
    todays_change_perc = snapshot.todays_change_percent

    return TickerSummary(
        ticker=ticker,
        name=company,
        last_price=last_price,
        todays_change_perc=todays_change_perc,
        query=serp_query,
        image_url=image_url,
        exchange=exchange,
    )
