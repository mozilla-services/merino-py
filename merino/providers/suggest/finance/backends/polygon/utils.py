"""Utilities for the Polygon backend"""

from typing import Any
from types import MappingProxyType

from pydantic import HttpUrl
from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary

# Source of truth for ticker symbol and company name mapping.
_TICKER_COMPANY = {
    "AAPL": "Apple Inc.",
    "AAL": "American Airlines Group Inc.",
    "ABBV": "AbbVie Inc.",
    "ABDE": "Adobe Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "AVGO": "Broadcom Inc.",
    "BAC": "Bank of America Corporation",
    "BA": "The Boeing Company",
    "BRK.B": "Berkshire Hathaway Inc.",
    "COIN": "Coinbase Global, Inc.",
    "COST": "Costco Wholesale Corporation",
    "CRM": "Salesforce, Inc.",
    "CVX": "Chevron Corporation",
    "DIS": "The Walt Disney Company",
    "GOOGL": "Alphabet Inc.",
    "HD": "The Home Depot, Inc.",
    "INTC": "Intel Corporation",
    "JNJ": "Johnson & Johnson",
    "JPM": "JPMorgan Chase & Co.",
    "KO": "The Coca-Cola Company",
    "LCID": "Lucid Group, Inc.",
    "LLY": "Eli Lilly and Company",
    "MA": "Mastercard Incorporated",
    "MCD": "McDonald's Corporation",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "MU": "Micron Technology, Inc.",
    "NFLX": "Netflix, Inc.",
    "NVDA": "NVIDIA Corporation",
    "PEP": "PepsiCo, Inc.",
    "PFE": "Pfizer Inc.",
    "PG": "Procter & Gamble Co.",
    "PLTR": "Palantir Technologies Inc.",
    "PLUG": "Plug Power Inc.",
    "PYPL": "PayPal Holdings, Inc.",
    "QCOM": "Qualcomm Incorporated",
    "RBLX": "Roblox Corporation",
    "SOFI": "SoFi Technologies, Inc.",
    "TSLA": "Tesla, Inc.",
    "TXN": "Texas Instruments Incorporated",
    "UNH": "UnitedHealth Group Incorporated",
    "V": "Visa Inc.",
    "WMT": "Walmart Inc.",
    "XOM": "Exxon Mobil Corporation",
}

# This will make sure that TICKER_COMPANY variable is read-only and immutable at runtime.
TICKER_COMPANY = MappingProxyType(_TICKER_COMPANY)

# Extracting just the ticker symbols into a separate set.
TICKERS = set(_TICKER_COMPANY.keys())


def is_valid_ticker(symbol: str) -> bool:
    """Check if the symbol provided is a valid and supported ticker."""
    return symbol.upper() in TICKERS


def lookup_ticker_company(ticker: str) -> str:
    """Get the ticker company."""
    return TICKER_COMPANY[ticker.upper()]


def extract_ticker_snapshot(data: dict[str, Any] | None) -> TickerSnapshot | None:
    """Extract the TickerSnapshot from the nested JSON response."""
    if data is None:
        return None
    else:
        ticker_info = data["ticker"]
        todays_change_perc = f'{ticker_info["todaysChangePerc"]:.2f}'
        last_price = f'{ticker_info["lastQuote"]["P"]:.2f}'

        return TickerSnapshot(todays_change_perc=todays_change_perc, last_price=last_price)


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
