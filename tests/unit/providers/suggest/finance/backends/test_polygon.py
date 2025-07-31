# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon backend module."""

import orjson
import logging
import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture
from typing import Any, cast
from tests.types import FilterCaplogFixture
from pytest import LogCaptureFixture

from merino.providers.suggest.finance.backends import PolygonBackend
from merino.providers.suggest.finance.backends.protocol import TickerSummary

URL_SINGLE_TICKER_SNAPSHOT = "/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"


@pytest.fixture(name="polygon_parameters")
def fixture_polygon_parameters(mocker: MockerFixture, statsd_mock: Any) -> dict[str, Any]:
    """Create constructor parameters for Polygon backend module."""
    return {
        "api_key": "api_key",
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "metrics_sample_rate": 1,
        "url_param_api_key": "apiKey",
        "url_single_ticker_snapshot": URL_SINGLE_TICKER_SNAPSHOT,
    }


@pytest.fixture(name="polygon")
def fixture_polygon(
    polygon_parameters: dict[str, Any],
) -> PolygonBackend:
    """Create a Polygon backend module object."""
    return PolygonBackend(**polygon_parameters)


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
            "todaysChangePerc": 0.82,
            "updated": 1605195918306274000,
        },
    }


@pytest.fixture(name="ticker_summary")
def fixture_ticker_summary() -> TickerSummary:
    """Create a ticker summary object for AAPL."""
    # these values are based on the above single_ticker_snapshot_response fixture.
    return TickerSummary(
        ticker="AAPL",
        name="Apple Inc.",
        last_price="$120.47 USD",
        todays_change_perc="0.82",
        query="AAPL stock",
    )


@pytest.mark.asyncio
async def test_fetch_ticker_snapshot_success(
    polygon: PolygonBackend, single_ticker_snapshot_response: dict[str, Any]
) -> None:
    """Test fetch_ticker_snapshot method. Should return valid response json."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(single_ticker_snapshot_response),
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    expected = single_ticker_snapshot_response
    actual = await polygon.fetch_ticker_snapshot(ticker)

    assert actual is not None
    assert actual == expected
    assert actual["ticker"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_fetch_ticker_snapshot_failure_for_http_500(
    polygon: PolygonBackend,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test fetch_ticker_snapshot method. Should raise for status on HTTPStatusError 500."""
    caplog.set_level(logging.WARNING)

    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=500,
        content=b"",
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    _ = await polygon.fetch_ticker_snapshot(ticker)

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.finance.backends.polygon.backend"
    )

    assert len(caplog.records) == 1

    assert records[0].message.startswith("Polygon request error")
    assert "500 Internal Server Error" in records[0].message


@pytest.mark.asyncio
async def test_get_ticker_summary_success(
    polygon: PolygonBackend,
    single_ticker_snapshot_response: dict[str, Any],
    ticker_summary: TickerSummary,
) -> None:
    """Test get_ticker_summary method. Should return valid TickerSummary object."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(single_ticker_snapshot_response),
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    expected = ticker_summary
    actual = await polygon.get_ticker_summary(ticker)

    assert actual is not None
    assert actual == expected


@pytest.mark.asyncio
async def test_get_ticker_summary_failure_returns_none(polygon: PolygonBackend) -> None:
    """Test get_ticker_summary. Should return None when snapshot request returns HTTP 500."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=500,
        content=b"",
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    actual = await polygon.get_ticker_summary(ticker)

    assert actual is None
