# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Google Suggest provider."""

import logging
from typing import Any

from fastapi import HTTPException

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


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location()


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
    geolocation: Location,
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

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(
            query="test",
            geolocation=geolocation,
            google_suggest_params="client%30firefox%26q%30test",
        )
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_suggestion_failed(
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the query method provides an empty list upon a backend error."""
    backend_mock.fetch.side_effect = BackendError("A backend error")

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(
            query="test",
            geolocation=geolocation,
            google_suggest_params="client%30firefox%26q%30test",
        )
    )

    assert suggestions == []
