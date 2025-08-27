# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon utils module."""

import pytest
from typing import Any

from merino.providers.suggest.finance.backends.polygon.utils import (
    build_ticker_summary,
    lookup_ticker_company,
    lookup_ticker_exchange,
    extract_snapshot_if_valid,
    get_tickers_for_query,
)

from merino.providers.suggest.finance.backends.protocol import TickerSnapshot, TickerSummary


@pytest.fixture(name="single_ticker_snapshot_response")
def fixture_single_ticker_snapshot_response() -> dict[str, Any]:
    """Sample response for single ticker snapshot request."""
    return {
        "results": [
            {
                "market_status": "open",
                "name": "Apple Inc",
                "ticker": "AAPL",
                "type": "stocks",
                "session": {
                    "change": 2.588,
                    "change_percent": 0.82,
                    "early_trading_change": 0,
                    "early_trading_change_percent": 0,
                    "regular_trading_change": 2.01,
                    "regular_trading_change_percent": 1.159,
                    "late_trading_change": 0.578,
                    "late_trading_change_percent": 0.329,
                    "close": 175.51,
                    "high": 176.63,
                    "low": 175.02,
                    "open": 176.04,
                    "volume": 46632535,
                    "previous_close": 173.5,
                    "price": 176.0883,
                    "last_updated": 1753833601079793200,
                    "vwap": 175.8562,
                },
                "last_quote": {
                    "last_updated": 1753833599239197400,
                    "timeframe": "REAL-TIME",
                    "ask": 176.09,
                    "ask_size": 3,
                    "ask_exchange": 12,
                    "bid": 176.05,
                    "bid_size": 1,
                    "bid_exchange": 12,
                },
                "last_trade": {
                    "last_updated": 1753833599213779700,
                    "timeframe": "REAL-TIME",
                    "id": "593866",
                    "price": 120.47,
                    "size": 48,
                    "exchange": 4,
                    "conditions": [12, 37],
                },
                "last_minute": {
                    "close": 176.08,
                    "high": 176.1,
                    "low": 176.04,
                    "transactions": 133,
                    "open": 176.04,
                    "volume": 25313,
                    "vwap": 176.0761,
                    "last_updated": 1753833601079793200,
                },
            }
        ],
        "status": "OK",
        "request_id": "cef2c957341a8e50b6455a7b8ef9702e",
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


def test_get_tickers_for_query() -> None:
    """Test get_tickers_for_query method for various cases."""
    # Valid stock ticker.
    assert get_tickers_for_query("AAPL") == ["AAPL"]

    # Valid ETF ticker.
    assert get_tickers_for_query("BIS") == ["BIS"]

    # Valid stock keywords.
    assert get_tickers_for_query("jpmorgan chase stock") == ["JPM"]

    # Valid ETF keywords.
    assert get_tickers_for_query("dow jones industrial average") == ["DIA", "DJD", "SCHD"]

    # Invalid ticker.
    assert get_tickers_for_query("BOB") is None

    # Invalid stock keywords.
    assert get_tickers_for_query("bobs burgers stock") is None

    # Invalid ETF keywords.
    assert get_tickers_for_query("bobs burgers stock index fund") is None


def test_extract_snapshot_if_valid_success(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected = TickerSnapshot(ticker="AAPL", last_price="120.47", todays_change_perc="+0.82")
    actual = extract_snapshot_if_valid(single_ticker_snapshot_response)

    assert actual is not None
    assert actual == expected


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

    # modifying values to be int type instead of float
    invalid_json_response["ticker"]["todaysChangePerc"] = 5
    invalid_json_response["ticker"]["lastTrade"]["P"] = 5

    assert extract_snapshot_if_valid(invalid_json_response) is None


def test_extract_snapshot_if_valid_returns_none_for_missing_property(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return None when
    snapshot json structure is invalid.
    """
    invalid_json_response = single_ticker_snapshot_response

    # modifying values to have a missing property
    del invalid_json_response["ticker"]["todaysChangePerc"]

    assert extract_snapshot_if_valid(invalid_json_response) is None


def test_build_ticker_summary_success() -> None:
    """Test build_ticker_summary method."""
    actual = build_ticker_summary(
        snapshot=TickerSnapshot(ticker="AAPL", last_price="120.47", todays_change_perc="+0.82"),
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
