# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the geolocation provider module."""

from typing import Any

import pytest
from pydantic import HttpUrl

from merino.middleware.geolocation import Location, Coordinates
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.custom_details import CustomDetails, GeolocationDetails
from merino.providers.suggest.geolocation.provider import Provider, Suggestion


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        country_name="United States",
        regions=["CA"],
        region_names=["California"],
        city="San Francisco",
        dma=807,
        postal_code="94105",
        coordinates=Coordinates(latitude=37.7739, longitude=-122.4313, radius=22),
    )


@pytest.fixture(name="empty_region")
def fixture_empty_region() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        country_name="United States",
        regions=None,
        region_names=None,
        city="San Francisco",
        dma=807,
        postal_code="94105",
        coordinates=Coordinates(latitude=37.7739, longitude=-122.4313, radius=22),
    )


@pytest.fixture(name="provider")
def fixture_provider(statsd_mock: Any) -> Provider:
    """Create a geolocation Provider for test."""
    return Provider()


@pytest.mark.asyncio
async def test_query_geolocation(provider: Provider, geolocation: Location) -> None:
    """Test that the query method provides a valid geolocation suggestion."""
    expected_suggestions: list[BaseSuggestion] = [
        Suggestion(
            provider="geolocation",
            title="",
            url=HttpUrl("https://merino.services.mozilla.com/"),
            is_sponsored=False,
            score=0,
            custom_details=CustomDetails(
                geolocation=GeolocationDetails(
                    country="United States",
                    region="California",
                    region_code="CA",
                    country_code="US",
                    city="San Francisco",
                    location=Coordinates(latitude=37.7739, longitude=-122.4313, radius=22),
                )
            ),
        )
    ]

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_geolocation_empty_region(provider: Provider, empty_region: Location) -> None:
    """Test that the query method provides a valid geolocation suggestion."""
    expected_suggestions: list[BaseSuggestion] = [
        Suggestion(
            provider="geolocation",
            title="",
            url=HttpUrl("https://merino.services.mozilla.com/"),
            is_sponsored=False,
            score=0,
            custom_details=CustomDetails(
                geolocation=GeolocationDetails(
                    country="United States",
                    country_code="US",
                    city="San Francisco",
                    location=Coordinates(latitude=37.7739, longitude=-122.4313, radius=22),
                )
            ),
        )
    ]

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=empty_region)
    )

    assert suggestions == expected_suggestions
