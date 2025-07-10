"""Utilities for the Polygon backend"""

from enum import StrEnum
from dataclasses import dataclass
from typing import Any, Dict


class FinanceEntityType(StrEnum):
    """Enum for the entity type for a finance suggestion request."""

    STOCK = "stock"
    INDEX = "index"


# TODO: subject to change
class TickerSymbol(StrEnum):
    """Enum for the stock ticker symbol."""

    AAPL = "AAPL"
    ABBV = "ABBV"
    AMD = "AMD"
    AMZN = "AMZN"
    BAC = "BAC"
    BRK_B = "BRK.B"  # The actual ticker symbol is BRK.B but we cannot have an enum key with dot notation
    COST = "COST"
    CRM = "CRM"
    GOOGL = "GOOGL"
    HD = "HD"
    INTC = "INTC"
    JNJ = "JNJ"
    JPM = "JPM"
    MA = "MA"
    META = "META"
    MSFT = "MSFT"
    NFLX = "NFLX"
    NVDA = "NVDA"
    PG = "PG"
    PLTR = "PLTR"
    TSLA = "TSLA"
    UNH = "UNH"
    V = "V"
    WMT = "WMT"
    XOM = "XOM"

    @classmethod
    def from_str(cls, symbol: str):
        try:
            return cls[symbol.upper()]
        except KeyError:
            return None



class IndexFund(StrEnum):
    """Enum for the index fund ticker symbol."""

    DJIA = "DJIA"
    NASDAQ = "NASDAQ"
    RUSSELL2000 = "RUSSELL2000"
    SP100 = "SP100"
    SP500 = "SP500"


@dataclass
class TickerSnapshot:
    """Ticker Snapshot"""

    ticker: TickerSymbol
    todays_change_perc: float
    last_price: float


def extract_ticker_snapshot(data: Dict[str, Any]) -> TickerSnapshot:
    """Extract the TickerSnapshot from the nested JSON response."""
    ticker_info = data.get("ticker", {})

    return TickerSnapshot(
        ticker=ticker_info.get("ticker", ""),
        todays_change_perc=ticker_info.get("todaysChangePerc", 0.0),
        last_price=ticker_info.get("lastQuote", {}).get("P", 0.0),
    )
