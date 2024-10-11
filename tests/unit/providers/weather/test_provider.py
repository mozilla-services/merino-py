# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather provider module."""

from typing import Any
from unittest.mock import call
from fastapi import HTTPException

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


@pytest.fixture(name="weather_report")
def fixture_weather_report() -> WeatherReport:
    """Return a test WeatherReport."""
    return WeatherReport(
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


@pytest.mark.asyncio
async def test_query_with_city_region_country_weather_report_returned(
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the query method provides a valid weather suggestion when city, region
    & country params are provided.
    """
    report: WeatherReport = WeatherReport(
        city_name="Boston",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/boston-ma/"
                "02108/current-weather/348735?lang=en-us"
            ),
            summary="Sunny",
            icon_id=1,
            temperature=Temperature(c=16, f=61),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/boston-ma/"
                "02108/daily-weather-forecast/348735?lang=en-us"
            ),
            summary="Expect showery weather Sunday afternoon through Monday morning",
            high=Temperature(c=20, f=68),
            low=Temperature(c=13, f=56),
        ),
        ttl=TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )

    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for Boston",
            url=HttpUrl(
                "https://www.accuweather.com/en/us/boston-ma/02108/current-weather/348735?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=0.3,
            description=None,
            icon=None,
            custom_details=CustomDetails(
                amo=None,
                geolocation=None,
                weather=WeatherDetails(weather_report_ttl=300),
            ),
            categories=None,
            city_name="Boston",
            current_conditions=CurrentConditions(
                url=HttpUrl(
                    "https://www.accuweather.com/en/us/boston-ma/02108/current-weather/348735?lang=en-us"
                ),
                summary="Sunny",
                icon_id=1,
                temperature=Temperature(c=16, f=61),
            ),
            forecast=Forecast(
                url=HttpUrl(
                    "https://www.accuweather.com/en/us/boston-ma/02108/daily-weather-forecast/348735?lang=en-us"
                ),
                summary="Expect showery weather Sunday afternoon through Monday morning",
                high=Temperature(c=20, f=68),
                low=Temperature(c=13, f=56),
            ),
        )
    ]

    backend_mock.get_weather_report.return_value = report

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(
            query="",
            geolocation=geolocation,
            city="Boston",
            country="US",
            region="MA",
            request_type="weather",
        )
    )

    assert suggestions == expected_suggestions


@pytest.mark.parametrize(
    ("city", "region", "country"),
    [
        (None, "MA", "US"),
        ("Boston", None, None),
        (None, "MA", None),
        (None, None, "US"),
        ("Boston", "MA", None),
    ],
    ids=[
        "missing_city",
        "missing_region_and_country",
        "missing_city_and_country",
        "missing_city_and_region",
        "missing_country",
    ],
)
@pytest.mark.asyncio
async def test_query_with_incomplete_city_region_country_params_fallback_to_initial_geolocation(
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
    weather_report: WeatherReport,
    city: str | None,
    region: str | None,
    country: str | None,
) -> None:
    """Test that the query method provides a weather suggestion without overwriting geolocation when city, region
    & country params are not all provided.
    """
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
            current_conditions=weather_report.current_conditions,
            forecast=weather_report.forecast,
            custom_details=CustomDetails(
                weather=WeatherDetails(weather_report_ttl=weather_report.ttl)
            ),
        )
    ]
    backend_mock.get_weather_report.return_value = weather_report

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(
            query="",
            city=city,
            region=region,
            country=country,
            request_type="weather",
            geolocation=geolocation,
        )
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
async def test_fetch_mapping(statsd_mock: Any, provider: Provider):
    """Test that pathfinder metric is recorded properly."""
    assert len(statsd_mock.gauge.call_args_list) == 0

    set_region_mapping("Canada", "Vancouver", "BC")
    await provider._fetch_mapping_size()

    assert len(statsd_mock.gauge.call_args_list) == 1
    assert statsd_mock.gauge.call_args_list == [
        call(name="providers.weather.pathfinder.mapping.size", value=1)
    ]
