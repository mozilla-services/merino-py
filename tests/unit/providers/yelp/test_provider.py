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
        "business_hours": [
            {
                "open": [
                    {"is_overnight": False, "start": "0700", "end": "2300", "day": 0},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 1},
                    {"is_overnight": False, "start": "0700", "end": "2300", "day": 2},
                    {"is_overnight": False, "start": "0700", "end": "2300", "day": 3},
                    {"is_overnight": False, "start": "0700", "end": "2300", "day": 4},
                    {"is_overnight": False, "start": "0800", "end": "2300", "day": 5},
                    {"is_overnight": False, "start": "0800", "end": "2300", "day": 6},
                ],
                "hours_type": "REGULAR",
                "is_open_now": True,
            }
        ],
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
            custom_details=CustomDetails(yelp=YelpDetails(**business_data)),
        ),
    ]
    backend_mock.get_businesses.return_value = business_data

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="cof", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions
