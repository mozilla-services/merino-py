# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the polygon (finance) provider."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.suggest.finance.backends.polygon.errors import (
    PolygonError,
    PolygonErrorMessages,
)
from merino.providers.suggest.finance.backends.protocol import (
    TickerMatch,
    TickerSnapshot,
    TickerSummary,
)
from merino.providers.suggest.finance.backends.polygon.etf_ticker_company_mapping import (
    STOCKS_WIDGET_DEFAULT_ETFS,
)
from merino.providers.suggest.finance.provider import Provider as FinanceProvider
from merino.providers.suggest.finance.backends import FinanceBackend


@pytest.fixture(name="provider_mock")
def fixture_provider_mock(mocker: MockerFixture) -> Any:
    """Create a FinanceProvider mock object."""
    provider = mocker.AsyncMock(spec=FinanceProvider)
    provider.get_image_url_for_ticker.return_value = None
    return provider


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a FinanceBackend mock object."""
    backend = mocker.AsyncMock(spec=FinanceBackend)
    backend.shutdown = mocker.AsyncMock()
    return backend


# NOTE: this fixture is required for test setup in conftest.py
@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any, statsd_mock: Any) -> dict[str, FinanceProvider]:
    """Define the finance provider used by the suggest endpoint."""
    provider = FinanceProvider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        score=0.8,
        name="polygon",
        query_timeout_sec=0.2,
        search_query_timeout_sec=settings.providers.polygon.search_query_timeout_sec,
        enabled_by_default=False,
        resync_interval_sec=60,
        cron_interval_sec=60,
    )

    return {"polygon": provider}


@pytest.fixture(name="AAPL_ticker_snapshot")
def fixture_AAPL_ticker_snapshot() -> TickerSnapshot:
    """AAPL ticker snapshot."""
    return TickerSnapshot(ticker="AAPL", last_trade_price="100", todays_change_percent="5.67")


@pytest.fixture(name="AAPL_ticker_summary")
def fixture_AAPL_ticker_summary() -> TickerSummary:
    """AAPL ticker summary."""
    return TickerSummary(
        ticker="AAPL",
        name="Apple Inc",
        last_price="$100 USD",
        todays_change_perc="+5.67",
        query="AAPL stock",
        image_url=None,
        exchange="NASDAQ",
    )


def test_suggest_for_finance_suggestion_returns_suggestion_for_valid_ticker(
    client: TestClient,
    backend_mock,
    AAPL_ticker_snapshot: TickerSnapshot,
    AAPL_ticker_summary: TickerSummary,
) -> None:
    """Test that the suggest endpoint returns a finance suggestion for a valid ticker."""
    # mock backend fetch_manifest_data method.
    backend_mock.fetch_manifest_data.return_value = (1, None)
    # mock backend get_snapshots method.
    backend_mock.get_snapshots.return_value = [AAPL_ticker_snapshot]
    # mock backend get_ticker_summary method.
    backend_mock.get_ticker_summary.return_value = AAPL_ticker_summary

    # testing for q="$AAPL"
    response = client.get("/api/v1/suggest?q=$AAPL&providers=polygon")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 1

    actual_ticker_summary = body["suggestions"][0]["custom_details"]["polygon"]["values"][0]

    assert actual_ticker_summary["ticker"] == "AAPL"
    assert actual_ticker_summary["name"] == "Apple Inc"
    assert actual_ticker_summary["last_price"] == "$100 USD"
    assert actual_ticker_summary["todays_change_perc"] == "+5.67"
    assert actual_ticker_summary["query"] == "AAPL stock"
    assert actual_ticker_summary["exchange"] == "NASDAQ"
    assert "image_url" not in actual_ticker_summary


def test_suggest_for_finance_suggestion_returns_no_suggestion_for_invalid_ticker(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint returns no finance suggestion for an invalid ticker."""
    # mock backend fetch_manifest_data method.
    backend_mock.fetch_manifest_data.return_value = (1, None)

    # not mocking any other backend methods since this should hit the branch in the provider
    # where it does not find a valid (supported) ticker and returns an empty list.

    # testing for q="$INVALID"
    response = client.get("/api/v1/suggest?q=$INVALID&providers=polygon")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 0


def test_suggest_finance_returns_default_etfs_for_newtab_source(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint returns the 4 default ETF suggestions when source=newtab and q is empty."""
    backend_mock.fetch_manifest_data.return_value = (1, None)

    etf_snapshots = [
        TickerSnapshot(ticker=ticker, last_trade_price="100", todays_change_percent="1.0")
        for ticker in STOCKS_WIDGET_DEFAULT_ETFS
    ]
    etf_summaries = [
        TickerSummary(
            ticker=ticker,
            name=f"{ticker} ETF",
            last_price="$100 USD",
            todays_change_perc="+1.0",
            query=f"{ticker} stock",
            image_url=None,
            exchange="NYSE",
        )
        for ticker in STOCKS_WIDGET_DEFAULT_ETFS
    ]
    backend_mock.get_snapshots.return_value = etf_snapshots
    backend_mock.get_ticker_summary.side_effect = etf_summaries

    response = client.get("/api/v1/suggest?q=&providers=polygon&source=newtab")

    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) == 1
    values = body["suggestions"][0]["custom_details"]["polygon"]["values"]
    assert len(values) == len(STOCKS_WIDGET_DEFAULT_ETFS)
    assert [v["ticker"] for v in values] == STOCKS_WIDGET_DEFAULT_ETFS


def test_suggest_finance_returns_400_for_empty_query_without_newtab_source(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint returns 400 when q is empty and source is not newtab."""
    backend_mock.fetch_manifest_data.return_value = (1, None)

    response = client.get("/api/v1/suggest?q=&providers=polygon")

    assert response.status_code == 400


def test_suggest_for_finance_suggestion_returns_no_suggestion_for_eager_match_blocked_ticker(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint returns no finance suggestion for a ticker that is on the eager match block list."""
    # mock backend fetch_manifest_data method.
    backend_mock.fetch_manifest_data.return_value = (1, None)

    # not mocking any other backend methods since this should hit the branch in the provider
    # where it does find a valid (supported) ticker but it is on the eager match block list, and returns an empty list.

    # testing for q="GOOG"
    response = client.get("/api/v1/suggest?q=GOOG&providers=polygon")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 0


def test_suggest_finance_newtab_returns_quote_for_unmapped_ticker(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that a newtab quote lookup resolves a symbol outside the curated mappings."""
    backend_mock.fetch_manifest_data.return_value = (1, None)
    backend_mock.get_snapshots.return_value = [
        TickerSnapshot(
            ticker="KLAR",
            last_trade_price="14.55",
            todays_change_percent="+2.14",
            name="Klarna Group plc",
        )
    ]
    backend_mock.get_ticker_summary.return_value = TickerSummary(
        ticker="KLAR",
        name="Klarna Group plc",
        last_price="$14.55 USD",
        todays_change_perc="+2.14",
        query="KLAR stock",
        image_url=None,
        exchange="",
    )

    response = client.get("/api/v1/suggest?q=klar&providers=polygon&source=newtab")

    assert response.status_code == 200
    backend_mock.get_snapshots.assert_awaited_once_with(["KLAR"])
    values = response.json()["suggestions"][0]["custom_details"]["polygon"]["values"]
    assert [(v["ticker"], v["name"], v["exchange"]) for v in values] == [
        ("KLAR", "Klarna Group plc", "")
    ]


def test_suggest_finance_newtab_rejects_symbol_list(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that a newtab quote lookup takes one symbol per request: a comma-separated
    list yields no suggestion and no backend call.
    """
    backend_mock.fetch_manifest_data.return_value = (1, None)

    response = client.get("/api/v1/suggest?q=HLN,AAPL&providers=polygon&source=newtab")

    assert response.status_code == 200
    assert response.json()["suggestions"] == []
    backend_mock.get_snapshots.assert_not_awaited()


def test_suggest_finance_ticker_search_returns_matches(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that a newtab ticker search returns candidate matches under polygon custom details."""
    backend_mock.fetch_manifest_data.return_value = (1, None)
    backend_mock.search_tickers.return_value = [
        TickerMatch(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", is_etf=False),
        TickerMatch(
            ticker="APLE", name="Apple Hospitality REIT, Inc.", exchange="NYSE", is_etf=False
        ),
    ]

    response = client.get(
        "/api/v1/suggest?q=apple&providers=polygon&source=newtab&request_type=ticker_search"
    )

    assert response.status_code == 200
    backend_mock.search_tickers.assert_awaited_once_with("apple")
    polygon = response.json()["suggestions"][0]["custom_details"]["polygon"]
    assert polygon["values"] == []
    assert polygon["matches"] == [
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "is_etf": False},
        {
            "ticker": "APLE",
            "name": "Apple Hospitality REIT, Inc.",
            "exchange": "NYSE",
            "is_etf": False,
        },
    ]


def test_suggest_finance_ticker_search_outlives_the_provider_query_timeout(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that ticker searches run under their own timeout budget: the upstream
    name search is slower than quote lookups and must not be cancelled by the
    keystroke-tuned provider timeout.
    """
    backend_mock.fetch_manifest_data.return_value = (1, None)

    async def slow_search(query: str) -> list[TickerMatch]:
        # Longer than the 0.2s provider query timeout used by the fixture.
        await asyncio.sleep(0.3)
        return [TickerMatch(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", is_etf=False)]

    backend_mock.search_tickers.side_effect = slow_search

    response = client.get(
        "/api/v1/suggest?q=apple&providers=polygon&source=newtab&request_type=ticker_search"
    )

    assert response.status_code == 200
    matches = response.json()["suggestions"][0]["custom_details"]["polygon"]["matches"]
    assert [m["ticker"] for m in matches] == ["AAPL"]


def test_suggest_finance_backend_error_yields_no_suggestions(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that a failed upstream request degrades to an empty response: the
    provider lets the error through for its circuit breaker and the handler
    drops the failed task.
    """
    backend_mock.fetch_manifest_data.return_value = (1, None)
    backend_mock.get_snapshots.side_effect = PolygonError(
        PolygonErrorMessages.HTTP_REQUEST_ERROR, operation="snapshot", detail="503"
    )

    response = client.get("/api/v1/suggest?q=AAPL&providers=polygon&source=newtab")

    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_suggest_finance_returns_400_for_unknown_request_type(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint rejects request_type values outside the allowed set."""
    backend_mock.fetch_manifest_data.return_value = (1, None)

    response = client.get(
        "/api/v1/suggest?q=apple&providers=polygon&source=newtab&request_type=bogus"
    )

    assert response.status_code == 400
