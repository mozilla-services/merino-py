"""Utilities for the Polygon backend"""

import logging
import re
from typing import Any
import hashlib

from pydantic import HttpUrl
from merino.configs import settings
from merino.providers.suggest.finance.backends.protocol import (
    TickerMatch,
    TickerSnapshot,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.polygon.stock_ticker_company_mapping import (
    ALL_STOCK_TICKER_COMPANY_MAPPING,
    STOCK_TICKER_EAGER_MATCH_BLOCKLIST,
)
from merino.providers.suggest.finance.backends.polygon.etf_ticker_company_mapping import (
    ALL_ETF_TICKER_COMPANY_MAPPING,
    ETF_TICKER_EAGER_MATCH_BLOCKLIST,
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

# This match either "stock(s) ABC" or "ABC stock(s)". Case insensitive.
STOCK_QUERY_PATTERN = re.compile(
    r"^(?:(?P<keyword1>\w+)\s+stocks?)$|^(?:stocks?\s+(?P<keyword2>\w+))$", re.IGNORECASE
)

# A single ticker symbol: uppercase alphanumerics with an optional share-class
# suffix ("BRK.B"). Accepts widget quote lookups.
TICKER_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,6}(?:[.\-][A-Z0-9]{1,3})?$")

# The equities universe served to the widget's ticker search, as upstream
# security type codes.
SEARCH_SECURITY_TYPES: frozenset[str] = frozenset(settings.providers.polygon.search_security_types)

# Exchange labels shown in suggestions, keyed by the MIC reported by the API.
# Unknown MICs fall back to the MIC itself.
MIC_DISPLAY_NAMES = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "ARCX": "NYSE",
    "BATS": "BATS",
    "XASE": "AMEX",
}


def get_tickers_for_query(query: str) -> list[str] | None:
    """Validate and return a list of tickers (1 to 3) or None."""
    query_upper = query.upper()

    # Early exit if the query is one of the eagerly matched tickers.
    # NOTE: These lists are subsets of `ALL_STOCK_TICKER_COMPANY_MAPPING` and `ALL_ETF_TICKER_COMPANY_MAPPING` lists.
    if (
        query_upper in STOCK_TICKER_EAGER_MATCH_BLOCKLIST
        or query_upper in ETF_TICKER_EAGER_MATCH_BLOCKLIST
    ):
        return None

    # If the query is a ticker from either stocks or ETFs tickers.
    # The above check prevents from eager matching for some tickers.
    if query_upper in ALL_STOCK_TICKER_COMPANY_MAPPING:
        return [query_upper]
    if query_upper in ALL_ETF_TICKER_COMPANY_MAPPING:
        return [query_upper]

    # If the query is a keyword from either stock or ETF keywords.
    if ticker := KEYWORD_TO_STOCK_TICKER_MAPPING.get(query):
        return [ticker]
    if tickers := KEYWORD_TO_ETF_TICKER_MAPPING.get(query):
        return tickers

    # If the query has the "stock(s)" keyword in it.
    if stock_query := STOCK_QUERY_PATTERN.match(query_upper):
        keyword = stock_query.group("keyword1") or stock_query.group("keyword2")
        if keyword in ALL_STOCK_TICKER_COMPANY_MAPPING:
            return [keyword]

        if keyword in ALL_ETF_TICKER_COMPANY_MAPPING:
            return [keyword]

    return None


def get_tickers_for_newtab_query(query: str) -> list[str] | None:
    """Return the single ticker symbol in a stocks widget query, or None.

    Widget lookups are not gated on the curated mappings: any well-formed
    symbol is passed through for a direct snapshot lookup. One symbol per
    request is deliberate. The approved use of the upstream API requires that
    a user's symbols are requested independently, so a list is not a symbol.
    """
    symbol = query.strip().upper()
    return [symbol] if TICKER_SYMBOL_PATTERN.match(symbol) else None


def extract_snapshot_if_valid(data: dict[str, Any] | None) -> TickerSnapshot | None:
    """Extract the TickerSnapshot from the nested JSON response, if it has the valid json structure.

    Unknown and delisted tickers come back as a result entry carrying an
    `error` key instead of session data. That is an expected outcome rather
    than a malformed response, so it yields None without a warning. So does
    an empty result, which is what the backend's circuit breaker substitutes
    for the upstream response while it is open.
    """
    if not data:
        return None

    try:
        result = data["results"][0]
        if "error" in result:
            return None
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

        if not isinstance(change_percent, (int, float)) or not isinstance(price, (int, float)):
            return None

        # Formatting the values to two decimal places (for float) and string type.
        todays_change_percent = (
            f"+{format_number(change_percent)}"
            if change_percent > 0
            else format_number(change_percent)
        )

        last_trade_price = format_number(price)
        name = result.get("name")

        return TickerSnapshot(
            ticker=ticker,
            todays_change_percent=todays_change_percent,
            last_trade_price=last_trade_price,
            name=name if isinstance(name, str) else None,
        )
    except KeyError, IndexError, TypeError:
        logger.warning(f"Polygon snapshot response json has incorrect shape: {data}")
        return None


def extract_ticker_matches_from_search_response(
    data: dict[str, Any] | None,
) -> list[TickerMatch]:
    """Extract widget search matches from a reference tickers search response.

    Keeps only active U.S. listings of the supported security types; anything
    else (warrants, units, foreign locales, delisted entries) is dropped.
    """
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []

    matches: list[TickerMatch] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        ticker = result.get("ticker")
        name = result.get("name")
        security_type = result.get("type")
        if (
            not isinstance(ticker, str)
            or not isinstance(name, str)
            or security_type not in SEARCH_SECURITY_TYPES
            or result.get("locale") != "us"
            or result.get("active") is not True
        ):
            continue
        mic = result.get("primary_exchange")
        matches.append(
            TickerMatch(
                ticker=ticker,
                name=name,
                exchange=MIC_DISPLAY_NAMES.get(mic, mic) if isinstance(mic, str) else "",
                is_etf=security_type == "ETF",
            )
        )
    return matches


def rank_ticker_matches(matches: list[TickerMatch], query: str) -> list[TickerMatch]:
    """Order search matches by relevance; the API returns them ordered by ticker.

    Exact symbol first, then symbols starting with the query, then names
    starting with the query (a leading "The " ignored), then common stock and
    ADRs ahead of ETFs. Ties keep the API order.
    """
    query_lower = query.strip().lower()
    query_upper = query_lower.upper()

    def tier(match: TickerMatch) -> tuple[bool, bool, bool, bool]:
        name = match.name.lower().removeprefix("the ")
        return (
            match.ticker != query_upper,
            not match.ticker.startswith(query_upper),
            not name.startswith(query_lower),
            match.is_etf,
        )

    return sorted(matches, key=tier)


def format_number(number: int | float) -> str:
    """Format float number to two decimal places. If int return as is."""
    if isinstance(number, float):
        return f"{number:.2f}"
    return str(number)  # int (or other non-float Real)


def build_ticker_summary(snapshot: TickerSnapshot, image_url: HttpUrl | None) -> TickerSummary:
    """Build a ticker summary for a finance suggestion response.

    Tickers outside the curated mappings (widget lookups) fall back to the
    company name reported by the snapshot; snapshots carry no exchange, so it
    is left empty for those.
    """
    ticker = snapshot.ticker
    entry = ALL_TICKER_COMPANY_MAPPING.get(ticker)
    company = str(entry["company"]) if entry else (snapshot.name or ticker)
    exchange = str(entry["exchange"]) if entry else ""
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


def generate_cache_key_for_ticker(ticker: str) -> str:
    """Generate cache key for a ticker."""
    hasher = hashlib.blake2s()
    hasher.update(ticker.upper().encode("utf-8"))
    ticker_hash = hasher.hexdigest()

    return f"PolygonBackend:v1:ticker_snapshot:{ticker_hash}"
