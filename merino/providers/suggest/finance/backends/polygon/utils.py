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
    TSLA = "TSLA"
    AMZN = "AMZN"
    MSFT = "MSFT"
    META = "META"
    GOOGL = "GOOGL"
    AMD = "AMD"
    PLTR = "PLTR"
    CRM = "CRM"
    V = "V"
    XOM = "XOM"
    UNH = "UNH"
    MA = "MA"
    COST = "COST"
    NFLX = "NFLX"
    WMT = "WMT"
    PG = "PG"
    HD = "HD"
    JNJ = "JNJ"
    ABBV = "ABBV"
    BAC = "BAC"
    JPM = "JPM"
    INTC = "INTC"
    NVDA = "NVDA"

    # The actual ticker symbol is BRK.B but we cannot have an enum key with dot notation
    BRK_B = "BRK.B"


class IndexFund(StrEnum):
    """Enum for the index fund ticker symbol."""

    SP500 = "SP500"
    DJIA = "DJIA"
    NASDAQ = "NASDAQ"
    RUSSELL2000 = "RUSSELL2000"
    SP100 = "SP100"
