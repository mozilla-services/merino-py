"""Utilities for the Polygon backend"""

from dataclasses import dataclass
from typing import Any, Dict
from types import MappingProxyType

# Source of truth for ticker symbol and company name mapping.
_TICKER_COMPANY = {
    "AAPL": "Apple Inc.",
    "ABBV": "AbbVie Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "BAC": "Bank of America Corporation",
    "BRK.B": "Berkshire Hathaway Inc.",
    "COST": "Costco Wholesale Corporation",
    "CRM": "Salesforce, Inc.",
    "GOOGL": "Alphabet Inc.",
    "HD": "The Home Depot, Inc.",
    "INTC": "Intel Corporation",
    "JNJ": "Johnson & Johnson",
    "JPM": "JPMorgan Chase & Co.",
    "MA": "Mastercard Incorporated",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "NFLX": "Netflix, Inc.",
    "NVDA": "NVIDIA Corporation",
    "PG": "Procter & Gamble Co.",
    "PLTR": "Palantir Technologies Inc.",
    "TSLA": "Tesla, Inc.",
    "UNH": "UnitedHealth Group Incorporated",
    "V": "Visa Inc.",
    "WMT": "Walmart Inc.",
    "XOM": "Exxon Mobil Corporation",
}

# This will make sure that TICKER_COMPANY variable is read-only and immutable at runtime.
TICKER_COMPANY = MappingProxyType(_TICKER_COMPANY)
TICKERS = set(_TICKER_COMPANY.keys())


def is_valid_ticker(symbol: str) -> bool:
    """TODO"""
    return symbol.upper() in TICKERS


def lookup_ticker_company(ticker: str) -> str:
    """Get the ticker company."""
    return TICKER_COMPANY[ticker.upper()]


@dataclass
class TickerSnapshot:
    """Ticker Snapshot"""

    todays_change_perc: str
    last_price: str


def extract_ticker_snapshot(data: Dict[str, Any]) -> TickerSnapshot:
    """Extract the TickerSnapshot from the nested JSON response."""
    ticker_info = data.get("ticker", {})

    return TickerSnapshot(
        todays_change_perc=ticker_info.get("todaysChangePerc", 0.0),
        last_price=ticker_info.get("lastQuote", {}).get("P", 0.0),
    )


def build_ticker_summary(ticker: str, snapshot: TickerSnapshot) -> dict[str, Any]:
    """TODO"""
    company = lookup_ticker_company(ticker)
    serp_query = f"{ticker} stock"
    last_price = f"${snapshot.last_price} USD"
    todays_change_perc = f"{snapshot.todays_change_perc:.2f}"

    return {
        "ticker": ticker,
        "name": company,
        "last_price": last_price,
        "todays_change_perc": todays_change_perc,
        "query": serp_query,
    }
