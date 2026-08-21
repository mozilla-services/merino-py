# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon utils module."""

import pytest
import copy
from typing import Any

from merino.providers.suggest.finance.backends.polygon.utils import (
    build_ticker_summary,
    lookup_ticker_company,
    lookup_ticker_exchange,
    extract_snapshot_if_valid,
    get_tickers_for_query,
    format_number,
)

from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary


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


def test_lookup_stock_ticker_company_success() -> None:
    """Test lookup_ticker_company method. Should return valid company name."""
    assert lookup_ticker_company("TSLA") == "Tesla Inc"


def test_lookup_etf_ticker_company_success() -> None:
    """Test lookup_ticker_company method. Should return valid company name."""
    assert lookup_ticker_company("VOO") == "Vanguard S&P 500 ETF"


def test_lookup_ticker_company_fail() -> None:
    """Test lookup_ticker_company method. Although this use case wouldn't happen at run time but we are still testing for it."""
    with pytest.raises(KeyError) as error:
        _ = lookup_ticker_company("BOB")
    assert error.typename == "KeyError"


def test_lookup_stock_ticker_exchange_success() -> None:
    """Test lookup_ticker_exchange method. Should return valid exchange name."""
    assert lookup_ticker_exchange("TSLA") == "NASDAQ"


def test_lookup_etf_ticker_exchange_success() -> None:
    """Test lookup_ticker_exchange method. Should return valid exchange name."""
    assert lookup_ticker_exchange("VOO") == "NYSE"


def test_lookup_ticker_exchange_fail() -> None:
    """Test lookup_ticker_exchange method. Although this use case wouldn't happen at run time but we are still testing for it."""
    with pytest.raises(KeyError) as error:
        _ = lookup_ticker_exchange("BOB")
    assert error.typename == "KeyError"


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


def test_extract_snapshot_if_valid_success(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected_market_open = TickerSnapshot(
        ticker="AAPL", last_trade_price="229.47", todays_change_percent="+0.82"
    )
    actual_market_open = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # should also validate for int values
    expected_market_open_with_int_values = TickerSnapshot(
        ticker="AAPL", last_trade_price="229", todays_change_percent="+0.82"
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
        ticker="AAPL", last_trade_price="229.31", todays_change_percent="+0.95"
    )
    actual_market_closed = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # setting the market status to early_trading.
    single_ticker_snapshot_response["results"][0]["market_status"] = "early_trading"
    expected_market_early_trading = TickerSnapshot(
        ticker="AAPL", last_trade_price="227.16", todays_change_percent="-0.13"
    )
    actual_market_early_trading = extract_snapshot_if_valid(single_ticker_snapshot_response)

    # setting the market status to late_trading.
    single_ticker_snapshot_response["results"][0]["market_status"] = "late_trading"
    # the change percent value is 0.946 from the fixture but the function rounds it to 2 decimal places.
    expected_market_late_trading = TickerSnapshot(
        ticker="AAPL", last_trade_price="229.31", todays_change_percent="+0.95"
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
