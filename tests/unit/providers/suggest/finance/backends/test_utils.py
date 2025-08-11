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
        "request_id": "657e430f1ae768891f018e08e03598d8",
        "status": "OK",
        "ticker": {
            "day": {
                "c": 120.4229,
                "h": 120.53,
                "l": 118.81,
                "o": 119.62,
                "v": 28727868,
                "vw": 119.725,
            },
            "lastQuote": {"P": 120.47, "S": 4, "p": 120.46, "s": 8, "t": 1605195918507251700},
            "lastTrade": {
                "c": [14, 41],
                "i": "4046",
                "p": 120.47,
                "s": 236,
                "t": 1605195918306274000,
                "x": 10,
            },
            "min": {
                "av": 28724441,
                "c": 120.4201,
                "h": 120.468,
                "l": 120.37,
                "n": 762,
                "o": 120.435,
                "t": 1684428720000,
                "v": 270796,
                "vw": 120.4129,
            },
            "prevDay": {
                "c": 119.49,
                "h": 119.63,
                "l": 116.44,
                "o": 117.19,
                "v": 110597265,
                "vw": 118.4998,
            },
            "ticker": "AAPL",
            "todaysChange": 0.98,
            "todaysChangePerc": 0.8201378182667601,
            "updated": 1605195918306274000,
        },
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
    """Test the get_tickers_for_query method. Should return correct ticker for a valid stock keyword."""
    assert get_tickers_for_query("jpmorgan chase stock") == "JPM"


def test_get_ticker_for_keyword_for_stock_fail() -> None:
    """Test the get_tickers_for_query method. Should return None for an invalid stock keyword."""
    assert get_tickers_for_query("bobs burgers stock") is None


# TODO: Will be updated once ETF tickers are assigned.
def test_get_ticker_for_keyword_for_etf_success() -> None:
    """Test the get_tickers_for_query method. Should return correct ticker for a valid ETF keyword."""
    assert get_tickers_for_query("dow jones industrial average") is None


def test_get_ticker_for_keyword_for_etf_fail() -> None:
    """Test the get_tickers_for_query method. Should return None for an invalid ETF keyword."""
    assert get_tickers_for_query("bobs burgers stock index fund") is None


def test_extract_snapshot_if_valid_success(
    single_ticker_snapshot_response: dict[str, Any],
) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected = TickerSnapshot(last_price="120.47", todays_change_perc="0.82")
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
        ticker="AAPL",
        snapshot=TickerSnapshot(last_price="120.47", todays_change_perc="0.82"),
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
