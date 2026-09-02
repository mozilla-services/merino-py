# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon utils module."""

import pytest
import copy
import logging
from typing import Any, Callable

from pytest import LogCaptureFixture

from merino.providers.suggest.finance.backends.polygon.utils import (
    build_ticker_summary,
    extract_snapshot_if_valid,
    extract_ticker_matches_from_search_response,
    get_tickers_for_newtab_query,
    get_tickers_for_query,
    format_number,
    rank_ticker_matches,
)

from merino.providers.suggest.finance.backends.protocol import (
    TickerMatch,
    TickerSnapshot,
    TickerSummary,
)


@pytest.fixture(name="single_ticker_snapshot_response")
def fixture_single_ticker_snapshot_response() -> dict[str, Any]:
    """Sample response for single ticker snapshot request."""
    return {
        "results": [
            {
                "market_status": "open",
                "name": "Apple Inc.",
                "ticker": "AAPL",
                "type": "stocks",
                "session": {
                    "change": 2.31,
                    "change_percent": 0.82,
                    "early_trading_change": -0.29,
                    "early_trading_change_percent": -0.128,
                    "regular_trading_change": 2.15,
                    "regular_trading_change_percent": 0.946,
                    "late_trading_change": 0.16,
                    "late_trading_change_percent": 0.0698,
                    "close": 229.31,
                    "high": 229.49,
                    "low": 224.69,
                    "open": 226.87,
                    "volume": 54429562,
                    "previous_close": 227.16,
                    "price": 229.47,
                    "last_updated": 1756240441077677000,
                    "vwap": 228.20475,
                },
                "last_quote": {
                    "last_updated": 1756238399992857900,
                    "timeframe": "DELAYED",
                    "ask": 230,
                    "ask_size": 2,
                    "ask_exchange": 15,
                    "bid": 227.5,
                    "bid_size": 1,
                    "bid_exchange": 15,
                },
                "last_trade": {
                    "last_updated": 1756239373267552000,
                    "timeframe": "DELAYED",
                    "id": "12275",
                    "price": 120.47,
                    "size": 9,
                    "exchange": 15,
                    "conditions": [12, 37],
                },
                "last_minute": {
                    "close": 229.39,
                    "high": 229.391,
                    "low": 229.39,
                    "transactions": 11,
                    "open": 229.391,
                    "volume": 1029,
                    "vwap": 229.39002,
                    "last_updated": 1756240441077677000,
                },
                "fmv": 229.47,
            }
        ],
        "status": "OK",
        "request_id": "542d40fedaab4caabf414a165726f5dc",
    }


@pytest.mark.parametrize(
    "test_keyword, expected_tickers",
    [
        (
            "GOOG",
            None,
        ),  # Valid stock ticker but it's on the ticker match block list, should return None.
        ("DDOG", ["DDOG"]),
        ("BIS", ["BIS"]),
        ("jpmorgan chase stock", ["JPM"]),
        ("dow jones industrial average", ["DIA", "DJD", "SCHD"]),
        # Valid "stock(s)" containing keywords.
        # This tests AAPL ticker which is in the eager match blocklist but should work in this scenario.
        ("stock aapl", ["AAPL"]),
        ("stocks aapl", ["AAPL"]),
        ("aapl stock", ["AAPL"]),
        ("aapl stocks", ["AAPL"]),
        # Invalid ticker, stock and ETF keywords
        ("BOB", None),
        ("bobs burgers stocks", None),
        ("bobs burgers stock index fund", None),
    ],
)
def test_get_tickers_for_query(test_keyword, expected_tickers) -> None:
    """Test get_tickers_for_query method for various cases."""
    assert get_tickers_for_query(test_keyword) == expected_tickers


@pytest.mark.parametrize(
    "query, expected_tickers",
    [
        ("AAPL", ["AAPL"]),
        ("  aapl ", ["AAPL"]),  # Case and surrounding whitespace normalized.
        ("BRK.B", ["BRK.B"]),
        ("KLAR", ["KLAR"]),  # Not in the curated mappings; passed through as is.
        ("AAPL,KLAR", None),  # One symbol per request; lists are not symbols.
        ("apple stock", None),  # Keyword queries are not symbols.
        ("TOOLONGSYMBOL", None),
        ("", None),
    ],
    ids=[
        "plain",
        "lowercase_and_whitespace",
        "class_suffix",
        "unmapped_ticker",
        "symbol_list",
        "keyword_query",
        "too_long",
        "empty",
    ],
)
def test_get_tickers_for_newtab_query(query, expected_tickers) -> None:
    """Test get_tickers_for_newtab_query for various widget queries."""
    assert get_tickers_for_newtab_query(query) == expected_tickers


def test_extract_snapshot_if_valid_success(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected_market_open = TickerSnapshot(
        ticker="AAPL", last_trade_price="229.47", todays_change_percent="+0.82", name="Apple Inc."
    )
    actual_market_open = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # should also validate for int values
    expected_market_open_with_int_values = TickerSnapshot(
        ticker="AAPL", last_trade_price="229", todays_change_percent="+0.82", name="Apple Inc."
    )
    # deep copying the fixture to over write a value.
    single_ticker_snapshot_response_with_int_values = copy.deepcopy(
        single_ticker_snapshot_response
    )
    single_ticker_snapshot_response_with_int_values["results"][0]["session"]["price"] = 229
    actual_market_open_with_int_values = extract_snapshot_if_valid(
        single_ticker_snapshot_response_with_int_values
    )

    # setting the market status to closed.
    single_ticker_snapshot_response["results"][0]["market_status"] = "closed"
    # the change percent value is 0.946 from the fixture but the function rounds it to 2 decimal places.
    expected_market_closed = TickerSnapshot(
        ticker="AAPL", last_trade_price="229.31", todays_change_percent="+0.95", name="Apple Inc."
    )
    actual_market_closed = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # setting the market status to early_trading.
    single_ticker_snapshot_response["results"][0]["market_status"] = "early_trading"
    expected_market_early_trading = TickerSnapshot(
        ticker="AAPL", last_trade_price="227.16", todays_change_percent="-0.13", name="Apple Inc."
    )
    actual_market_early_trading = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # setting the market status to late_trading.
    single_ticker_snapshot_response["results"][0]["market_status"] = "late_trading"
    # the change percent value is 0.946 from the fixture but the function rounds it to 2 decimal places.
    expected_market_late_trading = TickerSnapshot(
        ticker="AAPL", last_trade_price="229.31", todays_change_percent="+0.95", name="Apple Inc."
    )
    actual_market_late_trading = extract_snapshot_if_valid(single_ticker_snapshot_response)

    assert actual_market_open is not None
    assert actual_market_open == expected_market_open
    assert actual_market_open_with_int_values == expected_market_open_with_int_values
    assert actual_market_early_trading == expected_market_early_trading
    assert actual_market_late_trading == expected_market_late_trading
    assert actual_market_closed == expected_market_closed


def test_extract_snapshot_if_valid_returns_none() -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return None when snapshot param is None."""
    assert extract_snapshot_if_valid(None) is None


def test_extract_snapshot_if_valid_returns_none_for_unknown_ticker(
    caplog: LogCaptureFixture,
) -> None:
    """Test extract_snapshot_if_valid with an unknown ticker. The API answers with an error
    entry instead of session data; that is expected and must not be logged as malformed.
    """
    caplog.set_level(logging.WARNING)
    response = {
        "results": [{"ticker": "ZZZZZZ", "error": "NOT_FOUND", "message": "Ticker not found."}],
        "status": "OK",
    }

    assert extract_snapshot_if_valid(response) is None
    assert not caplog.records


def test_extract_snapshot_if_valid_returns_none_for_invalid_value_type(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return None when
    snapshot json structure is invalid.
    """
    invalid_json_response = single_ticker_snapshot_response

    # modifying values to be string type instead of number (float / int)
    invalid_json_response["results"][0]["session"]["change_percent"] = "5"
    invalid_json_response["results"][0]["last_trade"]["price"] = "5.55"

    assert extract_snapshot_if_valid(invalid_json_response) is None


def test_extract_snapshot_if_valid_returns_none_for_missing_property(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return None when
    snapshot json structure is invalid.
    """
    invalid_json_response = single_ticker_snapshot_response

    # modifying values to have a missing property
    del invalid_json_response["results"][0]["session"]["change_percent"]

    assert extract_snapshot_if_valid(invalid_json_response) is None


@pytest.mark.parametrize(
    "response",
    [None, {}, {"results": "nope"}, {"results": [None, 42]}],
    ids=["none", "no_results", "results_not_a_list", "results_not_objects"],
)
def test_extract_ticker_matches_ignores_malformed_responses(response) -> None:
    """Test that malformed search responses yield nothing rather than raising."""
    assert extract_ticker_matches_from_search_response(response) == []


def test_extract_ticker_matches_from_search_response(
    search_result: Callable[..., dict[str, Any]],
) -> None:
    """Test that a reference search response yields only active U.S. matches of
    the supported security types, with exchange MICs mapped to display names.
    """
    response = {
        "results": [
            search_result("AAPL", "Apple Inc."),
            search_result(
                "VTI", "Vanguard Total Stock Market ETF", "ETF", primary_exchange="ARCX"
            ),
            # Unknown MIC falls back to the MIC itself.
            search_result("XYZ", "Block, Inc.", primary_exchange="XPHL"),
            search_result("AAPLW", "Apple Warrant", "WARRANT"),
            search_result("APC", "Apple Inc.", locale="de", primary_exchange="XFRA"),
            search_result("WBA", "Walgreens Boots Alliance, Inc.", active=False),
            {"ticker": None, "type": "CS", "locale": "us", "active": True},
        ],
        "status": "OK",
    }

    matches = extract_ticker_matches_from_search_response(response)

    assert matches == [
        TickerMatch(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", is_etf=False),
        TickerMatch(
            ticker="VTI", name="Vanguard Total Stock Market ETF", exchange="NYSE", is_etf=True
        ),
        TickerMatch(ticker="XYZ", name="Block, Inc.", exchange="XPHL", is_etf=False),
    ]


def _match(ticker: str, name: str, is_etf: bool = False) -> TickerMatch:
    return TickerMatch(ticker=ticker, name=name, exchange="NYSE", is_etf=is_etf)


@pytest.mark.parametrize(
    "query, matches, expected_tickers",
    [
        # GS: a stock whose name starts with the query once "The " is ignored. The
        # ETFs also carry the name prefix but rank below stocks. SACH is a
        # substring-only hit and ranks last.
        (
            "goldman sachs",
            [
                _match("AAAU", "Goldman Sachs Physical Gold ETF", is_etf=True),
                _match("GBIL", "Goldman Sachs Access Treasury 0-1 Year ETF", is_etf=True),
                _match("GS", "The Goldman Sachs Group, Inc."),
                _match("SACH", "Sachem Capital Corp."),
            ],
            ["GS", "AAAU", "GBIL", "SACH"],
        ),
        # An exact symbol outranks a name-prefix hit.
        (
            "ford",
            [_match("FORD", "Forward Industries, Inc."), _match("F", "Ford Motor Company")],
            ["FORD", "F"],
        ),
        # A symbol-prefix hit outranks a name-prefix hit.
        (
            "goog",
            [
                _match("ABCD", "Goog Corp"),
                _match("GOOGL", "Alphabet Inc. Class A"),
                _match("GOOG", "Alphabet Inc. Class C"),
            ],
            ["GOOG", "GOOGL", "ABCD"],
        ),
    ],
    ids=["name_prefix_and_type", "exact_symbol_first", "symbol_prefix_before_name_prefix"],
)
def test_rank_ticker_matches(
    query: str, matches: list[TickerMatch], expected_tickers: list[str]
) -> None:
    """Test the ranking tiers: exact symbol, symbol prefix, name prefix (a leading
    "The " ignored), stocks before ETFs, then API order.
    """
    assert [m.ticker for m in rank_ticker_matches(matches, query)] == expected_tickers


@pytest.mark.parametrize(
    "snapshot_name, expected_name",
    [("Klarna Group plc", "Klarna Group plc"), (None, "KLAR")],
    ids=["snapshot_name", "falls_back_to_symbol"],
)
def test_build_ticker_summary_for_unmapped_ticker(
    snapshot_name: str | None, expected_name: str
) -> None:
    """Test that tickers outside the curated mappings take the company name from
    the snapshot, or the symbol when the snapshot carries none, and no exchange.
    """
    actual = build_ticker_summary(
        snapshot=TickerSnapshot(
            ticker="KLAR",
            last_trade_price="40.50",
            todays_change_percent="+1.20",
            name=snapshot_name,
        ),
        image_url=None,
    )

    assert actual.name == expected_name
    assert actual.exchange == ""
    assert actual.query == "KLAR stock"


def test_build_ticker_summary_success() -> None:
    """Test build_ticker_summary method."""
    actual = build_ticker_summary(
        snapshot=TickerSnapshot(
            ticker="AAPL", last_trade_price="120.47", todays_change_percent="+0.82"
        ),
        image_url=None,
    )
    expected = TickerSummary(
        ticker="AAPL",
        name="Apple Inc",
        last_price="$120.47 USD",
        todays_change_perc="+0.82",
        query="AAPL stock",
        image_url=None,
        exchange="NASDAQ",
    )

    assert actual == expected


def test_format_number() -> None:
    """Test format_number method."""
    actual_formatted_float = format_number(123.456)
    actual_formatted_int = format_number(123)

    assert actual_formatted_float == "123.46"
    assert actual_formatted_int == "123"
