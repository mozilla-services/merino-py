# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the finance provider module."""

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from starlette.exceptions import HTTPException

from merino.middleware.geolocation import Location
from merino.providers.suggest.custom_details import CustomDetails, PolygonDetails
from merino.providers.suggest.finance.backends.protocol import (
    FinanceBackend,
    FinanceManifest,
    GetManifestResultCode,
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


def test_should_fetch_respects_interval(provider: Provider):
    """Test that _should_fetch returns False if not enough time has passed."""
    provider.last_fetch_at = time.time()
    provider.last_fetch_failure_at = None

    assert provider._should_fetch() is False


def test_should_fetch_after_interval(provider: Provider):
    """Test that _should_fetch returns True after interval has passed."""
    provider.last_fetch_at = time.time() - 4000  # > resync_interval_sec
    provider.last_fetch_failure_at = None

    assert provider._should_fetch() is True


def test_should_fetch_skips_after_failure(provider: Provider):
    """Test that _should_fetch returns False if a recent failure occurred."""
    provider.last_fetch_at = time.time() - 4000
    provider.last_fetch_failure_at = time.time() - 100  # failure < 1hr ago

    assert provider._should_fetch() is False


def test_should_upload_respects_interval(provider: Provider):
    """Test that _should_upload returns False if not enough time has passed."""
    provider.last_upload_at = time.time()
    provider.last_upload_failure_at = None

    assert provider._should_upload() is False


def test_should_upload_skips_after_failure(provider: Provider):
    """Test that _should_upload returns False if a recent failure occurred."""
    provider.last_upload_at = time.time() - 8000
    provider.last_upload_failure_at = time.time() - 60  # within 1hr

    assert provider._should_upload() is False


def test_should_upload_after_interval(provider: Provider):
    """Test that _should_upload returns True after interval has passed."""
    provider.last_upload_at = time.time() - 8000
    provider.last_upload_failure_at = None

    assert provider._should_upload() is True


@pytest.mark.asyncio
async def test_fetch_manifest_sets_last_fetch_and_clears_failure(provider, mocker):
    """Ensure _fetch_manifest updates last_fetch_at and clears last_fetch_failure_at on success."""
    mock_manifest = FinanceManifest(tickers={"AAPL": "https://cdn.example.com/aapl.png"})
    mocker.patch.object(
        provider.backend,
        "fetch_manifest_data",
        return_value=(GetManifestResultCode.SUCCESS, mock_manifest),
    )
    provider.last_fetch_failure_at = time.time() - 500

    before = time.time()
    await provider._fetch_manifest()
    after = time.time()

    assert provider.last_fetch_at >= before and provider.last_fetch_at <= after
    assert provider.last_fetch_failure_at is None


@pytest.mark.asyncio
async def test_fetch_manifest_sets_last_failure_on_error(provider, mocker):
    """Ensure _fetch_manifest sets last_fetch_failure_at if backend fails."""
    mocker.patch.object(
        provider.backend,
        "fetch_manifest_data",
        return_value=(GetManifestResultCode.FAIL, None),
    )

    await provider._fetch_manifest()

    assert provider.last_fetch_failure_at is not None


@pytest.mark.asyncio
async def test_upload_manifest_sets_last_upload_and_clears_failure(provider, mocker):
    """Ensure _upload_manifest updates last_upload_at and clears last_upload_failure_at on success."""
    mocker.patch.object(provider.backend, "build_and_upload_manifest_file", new_callable=AsyncMock)

    provider.last_upload_failure_at = time.time() - 1000

    before = time.time()
    await provider._upload_manifest()
    after = time.time()

    assert provider.last_upload_at >= before and provider.last_upload_at <= after
    assert provider.last_upload_failure_at is None


@pytest.mark.asyncio
async def test_upload_manifest_sets_last_failure_on_exception(provider, mocker):
    """Ensure _upload_manifest sets last_upload_failure_at if exception is raised."""
    mocker.patch.object(
        provider.backend,
        "build_and_upload_manifest_file",
        new_callable=AsyncMock,
        side_effect=RuntimeError("upload fail"),
    )

    await provider._upload_manifest()

    assert provider.last_upload_failure_at is not None
