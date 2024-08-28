# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather provider module."""

from typing import Any
from unittest.mock import call

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture

from merino.config import settings
from merino.middleware.geolocation import Location
from merino.providers.base import BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.weather.backends.accuweather.pathfinder import set_region_mapping
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherBackend,
    WeatherReport,
)
from merino.providers.weather.provider import Provider, Suggestion

TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC = 300


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        regions=["CA"],
        city="San Francisco",
        dma=807,
        postal_code="94105",
    )


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WeatherBackend mock object for test."""
    return mocker.AsyncMock(spec=WeatherBackend)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any, statsd_mock: Any) -> Provider:
    """Create a weather Provider for test."""
    return Provider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        name="weather",
        score=0.3,
        query_timeout_sec=0.2,
        cron_interval_sec=6000,
    )


def test_enabled_by_default(provider: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert provider.enabled_by_default is False


def test_not_hidden_by_default(provider: Provider) -> None:
    """Test for the hidden method."""
    assert provider.hidden() is False


@pytest.mark.asyncio
async def test_query_weather_report_returned(
    backend_mock: Any, provider: Provider, geolocation: Location
) -> None:
    """Test that the query method provides a valid weather suggestion."""
    report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
        ttl=TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )
    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for San Francisco",
            url=HttpUrl(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name=report.city_name,
            current_conditions=report.current_conditions,
            forecast=report.forecast,
            custom_details=CustomDetails(weather=WeatherDetails(weather_report_ttl=report.ttl)),
        )
    ]
    backend_mock.get_weather_report.return_value = report

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_no_weather_report_returned(
    backend_mock: Any, provider: Provider, geolocation: Location
) -> None:
    """Test that the query method doesn't provide a weather suggestion without a weather
    report.
    """
    expected_suggestions: list[Suggestion] = []
    backend_mock.get_weather_report.return_value = None

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_fetch_mapping(statsd_mock: Any, provider: Provider):
    """Test that pathfinder metric is recorded properly."""
    assert len(statsd_mock.gauge.call_args_list) == 0

    set_region_mapping("Canada", "Vancouver", "BC")
    await provider._fetch_mapping()

    assert len(statsd_mock.gauge.call_args_list) == 1
    assert statsd_mock.gauge.call_args_list == [
        call(name="providers.weather.pathfinder.size", value=1)
    ]
