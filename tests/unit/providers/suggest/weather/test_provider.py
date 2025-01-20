# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather provider module."""

import logging
from typing import Any
from unittest.mock import call
from fastapi import HTTPException

import pytest
from pytest import LogCaptureFixture
from pydantic import HttpUrl
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.middleware.geolocation import Location
from merino.providers.base import BaseSuggestion, SuggestionRequest
from merino.providers.custom_details import CustomDetails, WeatherDetails
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    set_region_mapping,
    clear_region_mapping,
    clear_skip_cities_mapping,
    increment_skip_cities_mapping,
)
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherBackend,
    WeatherReport,
)
from merino.providers.suggest.weather.provider import Provider, Suggestion
from tests.types import FilterCaplogFixture

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


@pytest.fixture(name="weather_report")
def fixture_weather_report() -> WeatherReport:
    """Return a test WeatherReport."""
    return WeatherReport(
        city_name="San Francisco",
        region_code="CA",
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
    statsd_mock: Any,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
    weather_report: WeatherReport,
) -> None:
    """Test that the query method provides a valid weather suggestion."""
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
            city_name=weather_report.city_name,
            region_code=weather_report.region_code,
            current_conditions=weather_report.current_conditions,
            forecast=weather_report.forecast,
            custom_details=CustomDetails(
                weather=WeatherDetails(weather_report_ttl=weather_report.ttl)
            ),
        )
    ]
    backend_mock.get_weather_report.return_value = weather_report

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions

    assert len(statsd_mock.increment.call_args_list) == 1
    assert statsd_mock.increment.call_args_list == [call("providers.weather.query.weather_report")]


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
async def test_query_with_no_request_type_param_returns_http_400(
    provider: Provider, geolocation: Location
) -> None:
    """Test that the query method throws a http 400 error when `q` param is provided but no
    `request_type` param is provided
    """
    with pytest.raises(HTTPException) as accuweather_error:
        await provider.query(SuggestionRequest(query="weather", geolocation=geolocation))

    expected_error_message = "400: Invalid query parameters: `request_type` is missing"

    assert expected_error_message == str(accuweather_error.value)


@pytest.mark.asyncio
async def test_fetch_mapping(
    statsd_mock: Any,
    provider: Provider,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
):
    """Test that pathfinder metric is recorded properly."""
    caplog.set_level(logging.INFO)

    assert len(statsd_mock.gauge.call_args_list) == 0

    clear_region_mapping()
    set_region_mapping("NL", "Andel", "NB")

    clear_skip_cities_mapping()
    increment_skip_cities_mapping("CA", "BC", "Vancouver")
    increment_skip_cities_mapping("CA", "BC", "Vancouver")

    await provider._fetch_mappings()

    assert len(statsd_mock.gauge.call_args_list) == 3
    assert statsd_mock.gauge.call_args_list == [
        call(name="providers.weather.pathfinder.mapping.size", value=1),
        call(name="providers.weather.skip_cities_mapping.total.size", value=2),
        call(name="providers.weather.skip_cities_mapping.unique.size", value=1),
    ]

    records = filter_caplog(caplog.records, "merino.providers.suggest.weather.provider")
    assert len(records) == 2
    assert [record.message for record in records] == [
        "Weather Successful Mapping Values: {('NL', 'Andel'): 'NB'}",
        "Weather Skip Cities: {('CA', 'BC', 'Vancouver'): 2}",
    ]
