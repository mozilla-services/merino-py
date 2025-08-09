"""Utilities for the Polygon backend"""

import logging
from typing import Any

from pydantic import HttpUrl
from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary
from merino.providers.suggest.finance.backends.polygon.ticker_company_mapping import (
    _TICKER_COMPANY,
)
from merino.providers.suggest.finance.backends.polygon.keyword_ticker_mapping import (
    ETF_TICKER_KEYWORDS,
    STOCK_TICKER_KEYWORDS,
    KEYWORD_TO_ETF_TICKER,
    KEYWORD_TO_STOCK_TICKER,
)

logger = logging.getLogger(__name__)

# Extracting just the ticker symbols into a separate set.
TICKERS = frozenset(_TICKER_COMPANY.keys())


def _is_valid_ticker(symbol: str) -> bool:
    """Check if the symbol provided is a valid and supported ticker."""
    return symbol.upper() in TICKERS


def get_ticker_if_valid(symbol: str) -> str | None:
    """Validate and return a ticker. Returns None if not a valid ticker symbol."""
    if _is_valid_ticker(symbol):
        return symbol.upper()
    else:
        return None


def lookup_ticker_company(ticker: str) -> str:
    """Get the ticker company."""
    return _TICKER_COMPANY[ticker.upper()]


def _is_valid_keyword_for_stock_ticker(keyword: str) -> bool:
    """Check if the keyword provided is one of the supported keywords for stock tickers."""
    return keyword in STOCK_TICKER_KEYWORDS


def _is_valid_keyword_for_etf_ticker(keyword: str) -> bool:
    """Check if the keyword provided is one of the supported keywords for ETF tickers."""
    return keyword in ETF_TICKER_KEYWORDS


def get_ticker_for_keyword(keyword: str) -> str | None:
    """Validate and return a ticker. Should return a ticker for stock keywords or ETF keywords or None."""
    if _is_valid_keyword_for_stock_ticker(keyword):
        return KEYWORD_TO_STOCK_TICKER[keyword]
    if _is_valid_keyword_for_etf_ticker(keyword):
        # TODO add logic for etf keywords
        return KEYWORD_TO_ETF_TICKER[keyword]
    else:
        return None


def extract_snapshot_if_valid(data: dict[str, Any] | None) -> TickerSnapshot | None:
    """Extract the TickerSnapshot from the nested JSON response, if it has the valid json structure."""
    match data:
        case None:
            return None
        case {
            "ticker": {
                "todaysChangePerc": float(todays_change),
                "lastTrade": {"p": float(last_price)},
            }
        }:
            return TickerSnapshot(
                todays_change_perc=f"{todays_change:.2f}", last_price=f"{last_price:.2f}"
            )
        case _:
            logger.warning(f"Polygon invalid ticker snapshot json response: {data}")
            return None


def build_ticker_summary(
    ticker: str, snapshot: TickerSnapshot, image_url: HttpUrl | None
) -> TickerSummary:
    """Build a ticker summary for a finance suggestion response."""
    company = lookup_ticker_company(ticker)
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
    )
