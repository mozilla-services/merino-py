"""Utilities for the Polygon backend"""

# import logging
from enum import StrEnum

# logger = logging.getLogger(__name__)


# TODO: subject to change
class RequestType(StrEnum):
    """Enum for the request type for a finance suggestion request."""

    STOCK = "stock"
    INDEX = "index"


class TickerSymbol(StrEnum):
    """Enum for the stock ticker symbol."""

    NVDA = "Nvidia"
    TSLA = "Tesla"
    AAPL = "Apple"
    AMZN = "Amazon"
    MSFT = "Microsoft"
    META = "Meta Platforms"
    GOOGL = "Alphabet Inc."
    AMD = "Advanced Micro Devices"
    PLTR = "Palantir Technologies"
    CRM = "Salesforce"
    V = "Visa"
    XOM = "ExxonMobil"
    UNH = "UnitedHealth Group"
    MA = "Mastercard"
    COST = "Costco"
    NFLX = "Netflix"
    WMT = "Walmart"
    PG = "Procter & Gamble"
    HD = "Home Depot"
    JNJ = "Johnson & Johnson"
    ABBV = "AbbVie"
    BAC = "Bank of America"
    JPM = "JPMorgan Chase"
    INTC = "Intel"

    # The actual ticker symbol is BRK.B but we cannot have an enum key with dot notation
    BRK_B = "Berkshire Hathaway"


class IndexFund(StrEnum):
    """Enum for the index fund ticker symbol."""

    SP500 = "S&P 500 Index"
    DJIA = "Dow Jones Industrial Average"
    NASDAQ = "Nasdaq Composite Index"
    RUSSELL2000 = "Russell 2000 Index"
    SP100 = "S&P 100 Index"
