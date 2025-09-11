# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Google Suggest provider."""

import logging
from typing import Any

from fastapi import HTTPException
from freezegun import freeze_time

import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.custom_details import CustomDetails, GoogleSuggestDetails
from merino.providers.suggest.google_suggest.backends.google_suggest import GoogleSuggestBackend
from merino.providers.suggest.google_suggest.backends.protocol import GoogleSuggestResponse
from merino.providers.suggest.google_suggest.provider import Provider
from tests.types import FilterCaplogFixture


CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = (
    settings.providers.google_suggest.circuit_breaker_failure_threshold
)
CIRCUIT_BREAKER_RECOVER_TIMEOUT_SEC: float = (
    settings.providers.google_suggest.circuit_breaker_recover_timeout_sec
)


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location()


@pytest.fixture(name="srequest")
def fixture_srequest(geolocation: Location) -> SuggestionRequest:
    """Return a test SuggestionRequest."""
    return SuggestionRequest(
        query="test",
        geolocation=geolocation,
        google_suggest_params="client%30firefox%26q%30test",
    )


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a GoogleSuggestBackend mock object for test."""
    return mocker.AsyncMock(spec=GoogleSuggestBackend)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any) -> Provider:
    """Create a Provider for test."""
    return Provider(
        backend=backend_mock,
        name=settings.providers.google_suggest.type,
        score=settings.providers.google_suggest.score,
    )


def test_enabled_by_default(provider: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert provider.enabled_by_default is False


def test_not_hidden_by_default(provider: Provider) -> None:
    """Test for the hidden method."""
    assert provider.hidden() is False


@pytest.mark.parametrize(
    "query, params, expected_msg",
    [
        ("test", None, "`google_suggest_params` is missing"),
        ("", "client%30firefox%26q%30", "`q` should not be empty"),
    ],
)
def test_query_with_invalid_params_returns_http_400(
    query: str,
    params: str | None,
    expected_msg: str,
    provider: Provider,
    geolocation: Location,
    caplog: pytest.LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that the query method throws a http 400 error with invalid request parameters."""
    caplog.set_level(logging.WARNING)

    with pytest.raises(HTTPException) as ex:
        provider.validate(
            SuggestionRequest(query=query, geolocation=geolocation, google_suggest_params=params)
        )

    expected_error_message = f"400: Invalid query parameters: {expected_msg}"

    assert expected_error_message == str(ex.value)

    records = filter_caplog(caplog.records, "merino.providers.suggest.google_suggest.provider")

    assert len(records) == 1
    assert records[0].message == f"HTTP 400: invalid query parameters, {expected_msg}"


@pytest.mark.asyncio
async def test_query_suggestion_returned(
    backend_mock: Any,
    provider: Provider,
    srequest: SuggestionRequest,
    google_suggest_response: GoogleSuggestResponse,
) -> None:
    """Test that the query method provides a valid Google Suggest suggestion."""
    expected_suggestions: list[BaseSuggestion] = [
        BaseSuggestion(
            title="Google Suggest",
            url=provider.url,
            provider=settings.providers.google_suggest.type,
            is_sponsored=False,
            score=settings.providers.google_suggest.score,
            custom_details=CustomDetails(
                google_suggest=GoogleSuggestDetails(suggestions=google_suggest_response)
            ),
        )
    ]

    backend_mock.fetch.return_value = google_suggest_response

    suggestions: list[BaseSuggestion] = await provider.query(srequest)

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_circuit_breaker_with_backend_error(
    backend_mock: Any,
    mocker: MockerFixture,
    provider: Provider,
    srequest: SuggestionRequest,
    google_suggest_response: GoogleSuggestResponse,
) -> None:
    """Test that the provider can behave as expected when the circuit breaker
    is triggered.
    """
    backend_mock.fetch.side_effect = BackendError("A backend error")

    with freeze_time("2025-09-10") as freezer:
        # Trigger the breaker by calling the endpoint for the `threshold` times.
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            try:
                _ = await provider.query(srequest)
            except BackendError:
                pass

        spy = mocker.spy(backend_mock, "fetch")

        # Make a few more requests and verify all of them get short circuited and served by the fallback function.
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            # No need for exception handling as it should not be raised anyway.
            _ = await provider.query(srequest)

        # You shall not pass!
        spy.assert_not_called()

        # Now tick the timer to advance for the recovery timeout seconds.
        freezer.tick(CIRCUIT_BREAKER_RECOVER_TIMEOUT_SEC + 1.0)

        # Clear the side effect to restore the normal behavior.
        backend_mock.fetch.side_effect = None
        backend_mock.fetch.return_value = google_suggest_response

        # The breaker should be `half-open` hence the request should hit the integration point,
        # and bring the breaker back to the `closed` state.
        suggestions = await provider.query(srequest)

        spy.assert_called_once()
        assert len(suggestions) == 1

        # Verify that all the subsequent requests can succeed as well.
        for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            suggestions = await provider.query(srequest)
            assert len(suggestions) == 1
