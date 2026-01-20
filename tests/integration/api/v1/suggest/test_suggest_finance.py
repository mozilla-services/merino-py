# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the massive (finance) provider."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.providers.suggest.finance.backends.protocol import (
    TickerSnapshot,
    TickerSummary,
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
        name="massive",
        query_timeout_sec=0.2,
        enabled_by_default=False,
        resync_interval_sec=60,
        cron_interval_sec=60,
    )

    return {"massive": provider}


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
    response = client.get("/api/v1/suggest?q=$AAPL&providers=massive")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 1

    actual_ticker_summary = body["suggestions"][0]["custom_details"]["massive"]["values"][0]

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
    response = client.get("/api/v1/suggest?q=$INVALID&providers=massive")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 0


def test_suggest_for_finance_suggestion_returns_no_suggestion_for_eager_match_blocked_ticker(
    client: TestClient,
    backend_mock,
) -> None:
    """Test that the suggest endpoint returns no finance suggestion for a ticker that is on the eager match block list."""
    # mock backend fetch_manifest_data method.
    backend_mock.fetch_manifest_data.return_value = (1, None)

    # not mocking any other backend methods since this should hit the branch in the provider
    # where it does find a valid (supported) ticker but it is on the eager match block list, and returns an empty list.

    # testing for q="AAPL"
    response = client.get("/api/v1/suggest?q=AAPL&providers=massive")

    assert response.status_code == 200
    body = response.json()

    assert len(body["suggestions"]) == 0
