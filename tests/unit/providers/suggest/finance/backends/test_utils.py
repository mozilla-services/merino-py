# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon utils module."""

import pytest
from typing import Any

from merino.providers.suggest.finance.backends.polygon.utils import (
    build_ticker_summary,
    _is_valid_ticker,
    lookup_ticker_company,
    extract_ticker_snapshot,
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


def test__is_valid_ticker_success() -> None:
    """Test the _is_valid_ticker method. Should return True for a valid ticker."""
    assert _is_valid_ticker("AAPL") is True


def test__is_valid_ticker_fail() -> None:
    """Test the _is_valid_ticker method. Should return False for an invalid ticker."""
    assert _is_valid_ticker("BOB") is False


def test_lookup_ticker_company_success() -> None:
    """Test lookup_ticker_company method. Should return valid company name."""
    assert lookup_ticker_company("TSLA") == "Tesla Inc"


def test_lookup_ticker_company_fail() -> None:
    """Test lookup_ticker_company method. Although this use case wouldn't happen at run time but we are still testing for it."""
    with pytest.raises(KeyError) as error:
        _ = lookup_ticker_company("BOB")
    assert error.typename == "KeyError"


def test_extract_ticker_snapshot_success(single_ticker_snapshot_response: dict[str, Any]) -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return TickerSnapshot object."""
    expected = TickerSnapshot(last_price="120.47", todays_change_perc="0.82")
    actual = extract_ticker_snapshot(single_ticker_snapshot_response)

    assert actual is not None
    assert actual == expected


def test_extract_ticker_snapshot_returns_none() -> None:
    """Test extract_ticker_snapshot_returns_none method. Should return None when snapshot param is None."""
    assert extract_ticker_snapshot(None) is None


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
