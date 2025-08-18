# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon utils module."""

import pytest
from typing import Any

from merino.providers.suggest.finance.backends.polygon.utils import (
    build_ticker_summary,
    lookup_ticker_company,
    extract_snapshot_if_valid,
    get_tickers_for_query,
    _is_valid_ticker as is_valid_ticker,
    _is_valid_keyword_for_stock_ticker as is_valid_keyword_for_stock_ticker,
    _is_valid_keyword_for_etf_ticker as is_valid_keyword_for_etf_ticker,
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


def test_is_valid_ticker_success() -> None:
    """Test the _is_valid_ticker method. Should return True for a valid ticker."""
    assert is_valid_ticker("AAPL") is True


def test_is_valid_ticker_fail() -> None:
    """Test the _is_valid_ticker method. Should return False for an invalid ticker."""
    assert is_valid_ticker("BOB") is False


def test_lookup_ticker_company_success() -> None:
    """Test lookup_ticker_company method. Should return valid company name."""
    assert lookup_ticker_company("TSLA") == "Tesla Inc"


def test_lookup_ticker_company_fail() -> None:
    """Test lookup_ticker_company method. Although this use case wouldn't happen at run time but we are still testing for it."""
    with pytest.raises(KeyError) as error:
        _ = lookup_ticker_company("BOB")
    assert error.typename == "KeyError"


def test_is_valid_keyword_for_stock_ticker_success() -> None:
    """Test the _is_valid_keyword_for_stock_ticker method. Should return True for a valid keyword."""
    assert is_valid_keyword_for_stock_ticker("jpmorgan chase stock") is True


def test_is_valid_keyword_for_stock_ticker_fail() -> None:
    """Test the _is_valid_keyword_for_stock_ticker method. Should return false for an invalid keyword."""
    assert is_valid_keyword_for_stock_ticker("bobs burgers stock") is False


def test_is_valid_keyword_for_etf_ticker_success() -> None:
    """Test the _is_valid_keyword_for_etf_ticker method. Should return True for a valid keyword."""
    assert is_valid_keyword_for_etf_ticker("nasdaq composite stock index") is True


def test_is_valid_keyword_for_etf_ticker_fail() -> None:
    """Test the _is_valid_keyword_for_etf_ticker method. Should return False for an invalid keyword."""
    assert is_valid_keyword_for_etf_ticker("bobs burgers index funds") is False


def test_get_ticker_for_keyword_for_stock_success() -> None:
    """Test the get_tickers_for_query method. Should return correct tickers for a valid stock keyword."""
    assert get_tickers_for_query("jpmorgan chase stock") == ["JPM"]


def test_get_ticker_for_keyword_for_stock_fail() -> None:
    """Test the get_tickers_for_query method. Should return None for an invalid stock keyword."""
    assert get_tickers_for_query("bobs burgers stock") is None


# TODO: Will be updated once ETF tickers are assigned.
def test_get_ticker_for_keyword_for_etf_success() -> None:
    """Test the get_tickers_for_query method. Should return correct ticker for a valid ETF keyword."""
    etf_tickers = get_tickers_for_query("dow jones industrial average")

    assert etf_tickers is not None
    assert set(etf_tickers) == set(["DIA", "DJD", "SCHD"])


def test_get_ticker_for_keyword_for_etf_fail() -> None:
    """Test the get_tickers_for_query method. Should return None for an invalid ETF keyword."""
    assert get_tickers_for_query("bobs burgers stock index fund") is None


def test_extract_snapshot_if_valid_success(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected = TickerSnapshot(ticker="AAPL", last_price="120.47", todays_change_perc="0.82")
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
        snapshot=TickerSnapshot(ticker="AAPL", last_price="120.47", todays_change_perc="0.82"),
        image_url=None,
    )
    expected = TickerSummary(
        ticker="AAPL",
        name="Apple Inc",
        last_price="$120.47 USD",
        todays_change_perc="0.82",
        query="AAPL stock",
        image_url=None,
    )

    assert actual == expected
