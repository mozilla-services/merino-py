"""Utilities for the Polygon backend"""

from enum import StrEnum


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


class IndexFund(StrEnum):
    """Enum for the index fund ticker symbol."""

    DJIA = "DJIA"
    NASDAQ = "NASDAQ"
    RUSSELL2000 = "RUSSELL2000"
    SP100 = "SP100"
    SP500 = "SP500"
