# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the finance provider module."""

from typing import Any

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from starlette.exceptions import HTTPException

from merino.middleware.geolocation import Location
from merino.providers.suggest.custom_details import CustomDetails, PolygonDetails
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceManifest,
    TickerSummary,
)
from merino.providers.suggest.finance.provider import (
    Provider,
    BaseSuggestion,
    SuggestionRequest,
)


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="CA",
        regions=["ON"],
        city="Toronto",
        dma=613,
        postal_code="M5G2B6",
    )


@pytest.fixture(name="ticker_summary")
def fixture_ticker_summar() -> TickerSummary:
    """Return a test TickerSummary."""
    return TickerSummary(
        name="Apple Inc.",
        ticker="AAPL",
        last_price="$100.5",
        todays_change_perc="1.5",
        query="AAPL stock",
        image_url=None,
    )


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a FinanceBackend mock object."""
    return mocker.AsyncMock(spec=FinanceBackend)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any, statsd_mock: Any) -> Provider:
    """Create a finance Provider"""
    return Provider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="finance",
        score=0.3,
        query_timeout_sec=0.2,
        cron_interval_sec=60,
        resync_interval_sec=3600,
    )


def test_enabled_by_default(provider: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert provider.enabled_by_default is False


def test_not_hidden_by_default(provider: Provider) -> None:
    """Test for the hidden method."""
    assert provider.hidden() is False


def test_validate_fails_on_missing_query_param(
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the validate method raises HTTP 400 execption."""
    with pytest.raises(HTTPException):
        provider.validate(SuggestionRequest(query="", geolocation=geolocation))


@pytest.mark.asyncio
async def test_query_ticker_summary_returned(
    backend_mock: Any,
    provider: Provider,
    ticker_summary: TickerSummary,
    geolocation: Location,
) -> None:
    """Test that the query method provides a valid finance suggestion when ticker symbol from query param is supported"""
    expected_suggestions: list[BaseSuggestion] = [
        BaseSuggestion(
            title="Finance Suggestion",
            url=HttpUrl(provider.url),
            provider=provider.name,
            is_sponsored=False,
            score=provider.score,
            custom_details=CustomDetails(polygon=PolygonDetails(values=[ticker_summary])),
        ),
    ]
    backend_mock.get_ticker_summary.return_value = ticker_summary

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="aapl", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_ticker_summary_not_returned(
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the query method provides no finance suggestion when ticker symbol from query param is not supported"""
    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="test", geolocation=geolocation)
    )

    assert suggestions == []


def test_get_image_url_for_ticker_found(provider: Provider):
    """Test that get_image_url_for_ticker returns the correct URL
    when the ticker is present in the manifest.
    """
    provider.manifest_data = FinanceManifest(tickers={"AAPL": "https://cdn.example.com/aapl.png"})

    result = provider.get_image_url_for_ticker("AAPL")
    assert result == HttpUrl("https://cdn.example.com/aapl.png")


def test_get_image_url_for_ticker_found_case_insensitive(provider: Provider):
    """Test that get_image_url_for_ticker handles lowercase input
    and still returns the correct URL.
    """
    provider.manifest_data = FinanceManifest(tickers={"AAPL": "https://cdn.example.com/aapl.png"})

    result = provider.get_image_url_for_ticker("aapl")
    assert result == HttpUrl("https://cdn.example.com/aapl.png")


def test_get_image_url_for_ticker_not_found(provider: Provider):
    """Test that get_image_url_for_ticker returns an empty string
    when the ticker is not in the manifest.
    """
    provider.manifest_data = FinanceManifest(
        tickers={"GOOGL": "https://cdn.example.com/googl.png"}
    )

    result = provider.get_image_url_for_ticker("AAPL")
    assert result is None


def test_get_image_url_for_ticker_empty_manifest(provider: Provider):
    """Test that get_image_url_for_ticker returns an empty string
    when the manifest is empty.
    """
    provider.manifest_data = FinanceManifest(tickers={})
    result = provider.get_image_url_for_ticker("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_query_appends_image_url_to_summary(
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
    mocker,
) -> None:
    """Test that the query method passes the correct image_url and includes it in the TickerSummary."""
    ticker = "AAPL"
    image_url = HttpUrl("https://cdn.example.com/aapl.png")
    provider.manifest_data = FinanceManifest(tickers={ticker: image_url})

    expected_summary = TickerSummary(
        ticker=ticker,
        name="Apple Inc.",
        last_price="$100.5",
        todays_change_perc="1.5",
        query="AAPL stock",
        image_url=image_url,
    )

    backend_mock.get_ticker_summary = mocker.AsyncMock(return_value=expected_summary)

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query=ticker, geolocation=geolocation)
    )

    backend_mock.get_ticker_summary.assert_awaited_once_with(ticker, image_url)

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.custom_details is not None
    assert suggestion.custom_details.polygon is not None
    summary = suggestion.custom_details.polygon.values[0]

    assert summary.ticker == ticker
    assert summary.image_url == image_url
