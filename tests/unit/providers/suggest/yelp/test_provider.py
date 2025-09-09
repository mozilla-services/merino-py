# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit test for the Yelp provider module."""

from typing import Any

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from starlette.exceptions import HTTPException

from merino.middleware.geolocation import Location
from merino.providers.suggest.base import SuggestionRequest, BaseSuggestion
from merino.providers.suggest.custom_details import CustomDetails, YelpDetails
from merino.providers.suggest.yelp.backends.yelp import YelpBackend
from merino.providers.suggest.yelp.provider import Provider


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


@pytest.fixture(name="business_data")
def fixture_business_data() -> dict:
    """Return a test business data."""
    return {
        "name": "MochaZilla",
        "url": "https://example.com",
        "address": "123 Firefox Drive",
        "rating": 4.8,
        "price": "$",
        "review_count": 22,
        "business_hours": {"start": "0700", "end": "2300"},
        "image_url": "https://example.com/image.png",
    }


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a YelpBackend mock object."""
    return mocker.AsyncMock(spec=YelpBackend)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any, statsd_mock: Any) -> Provider:
    """Create a Yelp Provider"""
    return Provider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="yelp",
        score=0.26,  # TODO confirm value
        query_timeout_sec=0.2,
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


def test_validate_fails_on_empty_query(
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the validate method raises HTTP 400 exception for empty query."""
    with pytest.raises(HTTPException) as exc_info:
        provider.validate(SuggestionRequest(query="", geolocation=geolocation))

    assert exc_info.value.status_code == 400
    assert "q` is missing" in exc_info.value.detail


def test_validate_fails_on_whitespace_query(
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the validate method raises HTTP 400 exception for whitespace-only query."""
    with pytest.raises(HTTPException) as exc_info:
        provider.validate(SuggestionRequest(query="   ", geolocation=geolocation))

    assert exc_info.value.status_code == 400
    assert "Valid query and location are required" in exc_info.value.detail


def test_validate_fails_on_geolocation_without_city(
    provider: Provider,
) -> None:
    """Test that the validate method raises HTTP 400 exception when geolocation has no city."""
    geolocation_no_city = Location(
        country="CA",
        regions=["ON"],
        city=None,  # Missing city
        dma=613,
        postal_code="M5G2B6",
    )

    with pytest.raises(HTTPException) as exc_info:
        provider.validate(SuggestionRequest(query="coffeeshops", geolocation=geolocation_no_city))

    assert exc_info.value.status_code == 400
    assert "Valid query and location are required" in exc_info.value.detail


def test_validate_passes_with_valid_request(
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the validate method passes with valid request."""
    # Should not raise any exception
    provider.validate(SuggestionRequest(query="coffeeshops", geolocation=geolocation))


@pytest.mark.asyncio
async def test_query_returns_empty_when_no_business(
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the query method returns empty list when no business is found."""
    backend_mock.get_business.return_value = None

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="coffeeshops", geolocation=geolocation)
    )

    assert suggestions == []


@pytest.mark.asyncio
async def test_query_strips_whitespace_from_search_term(
    backend_mock: Any,
    provider: Provider,
    business_data: dict,
    geolocation: Location,
) -> None:
    """Test that the query method strips whitespace from search term."""
    backend_mock.get_business.return_value = business_data

    await provider.query(SuggestionRequest(query="  coffee  ", geolocation=geolocation))

    # Verify the backend was called with stripped search term
    backend_mock.get_business.assert_called_once_with("coffee", geolocation)


def test_build_suggestion_removes_url_from_data(
    provider: Provider,
    business_data: dict,
) -> None:
    """Test that build_suggestion removes URL from data and creates proper suggestion."""
    # Copy the data to avoid modifying the fixture
    data_copy = business_data.copy()

    suggestion = provider.build_suggestion(data_copy)

    assert suggestion is not None
    assert suggestion.title == "Yelp Suggestion"
    # HttpUrl normalizes URLs by adding trailing slashes
    assert str(suggestion.url) == "https://example.com/"
    assert suggestion.provider == "yelp"
    assert suggestion.is_sponsored is False
    assert suggestion.score == 0.26

    # Type assertions for mypy
    assert suggestion.custom_details is not None
    assert suggestion.custom_details.yelp is not None
    assert suggestion.custom_details.yelp.name == business_data["name"]

    # Verify URL was removed from the data
    assert "url" not in data_copy


@pytest.mark.asyncio
async def test_query_business_returned(
    backend_mock: Any,
    provider: Provider,
    business_data: dict,
    geolocation: Location,
) -> None:
    """Test that the query method provides a valid finance suggestion when ticker symbol from query param is supported"""
    expected_suggestions: list[BaseSuggestion] = [
        BaseSuggestion(
            title="Yelp Suggestion",
            url=HttpUrl(business_data["url"]),
            provider=provider.name,
            is_sponsored=False,
            score=provider.score,
            custom_details=CustomDetails(
                yelp=YelpDetails(
                    name=business_data["name"],
                    address=business_data["address"],
                    price=business_data["price"],
                    rating=business_data["rating"],
                    review_count=business_data["review_count"],
                    business_hours=business_data["business_hours"],
                    image_url=business_data["image_url"],
                )
            ),
        ),
    ]
    backend_mock.get_business.return_value = business_data

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="cof", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.parametrize(
    "search_term, expected",
    [
        # Category matches
        ("Coffeeshops near me", "coffeeshops"),
        ("ice cream & frozen yogurt", "ice cream & frozen yogurt"),
        # Bad location matches
        ("coffeeshops in the neighbourhood", "coffeeshops in the neighbourhood"),
        # Extra whitespace
        ("   coffeeshops nearby   ", "coffeeshops"),
    ],
)
def test_category_keyword_match(provider: Provider, search_term: str, expected: str) -> None:
    """Test that the category keyword match works as expected."""
    assert provider.normalize_query(search_term) == expected
