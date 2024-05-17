# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AccuWeather backend module."""
import datetime
import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Optional, cast
from unittest.mock import AsyncMock

import freezegun
import pytest
from httpx import AsyncClient, HTTPError, Request, Response
from pydantic import HttpUrl
from pytest import FixtureRequest, LogCaptureFixture
from pytest_mock import MockerFixture
from redis import RedisError
from redis.asyncio import Redis

from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError, CacheMissError
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.accuweather import (
    AccuweatherBackend,
    AccuweatherError,
    AccuweatherLocation,
    CurrentConditionsWithTTL,
    ForecastWithTTL,
    add_partner_code,
)
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)
from tests.types import FilterCaplogFixture

ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
TEST_CACHE_TTL_SEC = 1800
TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC = 300


@pytest.fixture(name="redis_mock_cache_miss")
def fixture_redis_mock_cache_miss(mocker: MockerFixture) -> Any:
    """Create a Redis client mock object for testing."""

    async def mock_get(key) -> Any:
        return None

    async def mock_set(key, value, **kwargs) -> Any:
        return None

    async def script_callable(keys, args) -> list:
        return []

    def mock_register_script(script) -> Callable[[list, list], Awaitable[list]]:
        return script_callable

    mock = mocker.AsyncMock(spec=Redis)
    mock.get.side_effect = mock_get
    mock.set.side_effect = mock_set
    mock.register_script.side_effect = mock_register_script
    return mock


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters(
    mocker: MockerFixture, statsd_mock: Any
) -> dict[str, Any]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "cached_location_key_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_current_condition_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_forecast_ttl_sec": TEST_CACHE_TTL_SEC,
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "url_param_api_key": "apikey",
        "url_postalcodes_path": "/locations/v1/postalcodes/{country_code}/search.json",
        "url_postalcodes_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
        "url_location_key_placeholder": "{location_key}",
        "url_location_completion_path": "/locations/v1/{country_code}/autocomplete.json"
    }


@pytest.fixture(name="expected_weather_report")
def fixture_expected_weather_report() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
        ttl=TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )


@pytest.fixture(name="response_header")
def fixture_response_header() -> dict[str, str]:
    """Create a response header with a reasonable expiry."""
    expiry_time: datetime.datetime = datetime.datetime.now(
        tz=datetime.timezone.utc
    ) + datetime.timedelta(days=2)
    return {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}


@pytest.fixture(name="accuweather")
def fixture_accuweather(
    redis_mock_cache_miss: AsyncMock,
    accuweather_parameters: dict[str, Any],
) -> AccuweatherBackend:
    """Create an Accuweather object for test. This object always have cache miss."""
    return AccuweatherBackend(
        cache=RedisAdapter(redis_mock_cache_miss),
        **accuweather_parameters,
    )


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Create a Location object for test."""
    return Location(
        country="US", region="CA", city="San Francisco", dma=807, postal_code="94105"
    )


@pytest.fixture(name="accuweather_location_response")
def fixture_accuweather_location_response() -> bytes:
    """Return response content for AccuWeather postal code endpoint."""
    response: list[dict[str, Any]] = [
        {
            "Version": 1,
            "Key": "39376_PC",
            "Type": "PostalCode",
            "Rank": 35,
            "LocalizedName": "San Francisco",
            "EnglishName": "San Francisco",
            "PrimaryPostalCode": "94105",
            "Region": {
                "ID": "NAM",
                "LocalizedName": "North America",
                "EnglishName": "North America",
            },
            "Country": {
                "ID": "US",
                "LocalizedName": "United States",
                "EnglishName": "United States",
            },
            "AdministrativeArea": {
                "ID": "CA",
                "LocalizedName": "California",
                "EnglishName": "California",
                "Level": 1,
                "LocalizedType": "State",
                "EnglishType": "State",
                "CountryID": "US",
            },
            "TimeZone": {
                "Code": "PDT",
                "Name": "America/Los_Angeles",
                "GmtOffset": -7.0,
                "IsDaylightSaving": True,
                "NextOffsetChange": "2022-11-06T09:00:00Z",
            },
            "GeoPosition": {
                "Latitude": 37.792,
                "Longitude": -122.392,
                "Elevation": {
                    "Metric": {"Value": 19.0, "Unit": "m", "UnitType": 5},
                    "Imperial": {"Value": 62.0, "Unit": "ft", "UnitType": 0},
                },
            },
            "IsAlias": False,
            "ParentCity": {
                "Key": "347629",
                "LocalizedName": "San Francisco",
                "EnglishName": "San Francisco",
            },
            "SupplementalAdminAreas": [
                {
                    "Level": 2,
                    "LocalizedName": "San Francisco",
                    "EnglishName": "San Francisco",
                }
            ],
            "DataSets": [
                "AirQualityCurrentConditions",
                "AirQualityForecasts",
                "Alerts",
                "DailyAirQualityForecast",
                "DailyPollenForecast",
                "ForecastConfidence",
                "FutureRadar",
                "MinuteCast",
                "Radar",
            ],
        }
    ]
    return json.dumps(response).encode("utf-8")


@pytest.fixture(name="accuweather_cached_location_key")
def fixture_accuweather_cached_location_key() -> bytes:
    """Return response content for AccuWeather postal code endpoint."""
    location: dict[str, Any] = {
        "key": "39376_PC",
        "localized_name": "San Francisco",
    }
    return json.dumps(location).encode("utf-8")


@pytest.fixture(name="accuweather_current_conditions_response")
def fixture_accuweather_current_conditions_response() -> bytes:
    """Return response content for AccuWeather current conditions endpoint."""
    response: list[dict[str, Any]] = [
        {
            "LocalObservationDateTime": "2022-10-21T15:34:00-07:00",
            "EpochTime": 1666391640,
            "WeatherText": "Mostly cloudy",
            "WeatherIcon": 6,
            "HasPrecipitation": False,
            "PrecipitationType": None,
            "IsDayTime": True,
            "Temperature": {
                "Metric": {
                    "Value": 15.5,
                    "Unit": "C",
                    "UnitType": 17,
                },
                "Imperial": {
                    "Value": 60.0,
                    "Unit": "F",
                    "UnitType": 18,
                },
            },
            "MobileLink": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            "Link": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
        },
    ]
    return json.dumps(response).encode("utf-8")


@pytest.fixture(name="accuweather_cached_current_conditions")
def fixture_accuweather_cached_current_conditions() -> bytes:
    """Return the cached content for AccuWeather current conditions."""
    return json.dumps(
        {
            "url": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            "summary": "Mostly cloudy",
            "icon_id": 6,
            "temperature": {"c": 15.5, "f": 60.0},
        }
    ).encode("utf-8")


@pytest.fixture(name="accuweather_forecast_response")
def fixture_accuweather_forecast_response() -> dict[str, Any]:
    """Return response content for AccuWeather forecast endpoint.

    Note: Temperature is empty.
    """
    return {
        "Headline": {
            "EffectiveDate": "2022-10-01T08:00:00-07:00",
            "EffectiveEpochDate": 1664636400,
            "Severity": 4,
            "Text": "Pleasant Saturday",
            "Category": "mild",
            "EndDate": None,
            "EndEpochDate": None,
            "MobileLink": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            "Link": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
        },
        "DailyForecasts": [
            {
                "Date": "2022-09-28T07:00:00-07:00",
                "EpochDate": 1664373600,
                "Temperature": {},
                "Day": {"Icon": 4, "IconPhrase": "Clear", "HasPrecipitation": False},
                "Night": {
                    "Icon": 36,
                    "IconPhrase": "Intermittent clouds",
                    "HasPrecipitation": True,
                },
                "Sources": ["AccuWeather"],
                "MobileLink": (
                    "http://www.accuweather.com/en/us/san-francisco-ca/"
                    "94103/daily-weather-forecast/39376_pc?day=1&lang=en-us"
                ),
                "Link": (
                    "http://www.accuweather.com/en/us/san-francisco-ca/"
                    "94103/daily-weather-forecast/39376_pc?day=1&lang=en-us"
                ),
            }
        ],
    }


@pytest.fixture(name="accuweather_forecast_response_celsius")
def fixture_accuweather_forecast_response_celsius(
    accuweather_forecast_response: dict[str, Any]
) -> bytes:
    """Return response content for AccuWeather forecast endpoint in celsius."""
    accuweather_forecast_response["DailyForecasts"][0]["Temperature"] = {
        "Minimum": {"Value": 13.9, "Unit": "C", "UnitType": 17},
        "Maximum": {"Value": 21.1, "Unit": "C", "UnitType": 17},
    }
    return json.dumps(accuweather_forecast_response).encode("utf-8")


@pytest.fixture(name="accuweather_forecast_response_fahrenheit")
def fixture_accuweather_forecast_response_fahrenheit(
    accuweather_forecast_response: dict[str, Any]
) -> bytes:
    """Return response content for AccuWeather forecast endpoint in fahrenheit."""
    accuweather_forecast_response["DailyForecasts"][0]["Temperature"] = {
        "Minimum": {"Value": 57.0, "Unit": "F", "UnitType": 18},
        "Maximum": {"Value": 70.0, "Unit": "F", "UnitType": 18},
    }
    return json.dumps(accuweather_forecast_response).encode("utf-8")


@pytest.fixture(name="accuweather_cached_forecast_fahrenheit")
def fixture_accuweather_cached_forecast_fahrenheit() -> bytes:
    """Return the cached AccuWeather forecast in fahrenheit."""
    return json.dumps(
        {
            "url": (
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            "summary": "Pleasant Saturday",
            "high": {"f": 70.0},
            "low": {"f": 57.0},
        }
    ).encode("utf-8")


@pytest.fixture(name="accuweather_cached_data_hits")
def fixture_accuweather_cached_data_hits(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> list[Optional[bytes] | Optional[int]]:
    """Return the cached AccuWeather quartet for a cache hit."""
    return [
        accuweather_cached_location_key,
        accuweather_cached_current_conditions,
        accuweather_cached_forecast_fahrenheit,
        TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    ]


@pytest.fixture(name="accuweather_parsed_data_hits")
def fixture_accuweather_parsed_data_hits(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> tuple[
    Optional[AccuweatherLocation],
    Optional[CurrentConditions],
    Optional[Forecast],
    Optional[int],
]:
    """Return the cached AccuWeather triplet for a cache hit."""
    return (
        AccuweatherLocation.model_validate_json(accuweather_cached_location_key),
        CurrentConditions.model_validate_json(accuweather_cached_current_conditions),
        Forecast.model_validate_json(accuweather_cached_forecast_fahrenheit),
        TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )


@pytest.fixture(name="accuweather_cached_data_partial_hits")
def Fixture_accuweather_cached_data_partial_hits(
    accuweather_cached_location_key: bytes,
) -> list[Optional[bytes]]:
    """Return the parsed AccuWeather quartet for a partial cache miss."""
    return [accuweather_cached_location_key, None, None, None]


@pytest.fixture(name="accuweather_parsed_data_partial_hits")
def fixture_accuweather_parsed_data_partial_hits(
    accuweather_cached_location_key: bytes,
) -> tuple[
    Optional[AccuweatherLocation],
    Optional[CurrentConditions],
    Optional[Forecast],
    Optional[int],
]:
    """Return the partial parsed AccuWeather quartet for a cache hit."""
    return (
        AccuweatherLocation.model_validate_json(accuweather_cached_location_key),
        None,
        None,
        None,
    )


@pytest.fixture(name="accuweather_cached_data_partial_hits_left")
def Fixture_accuweather_cached_data_partial_hits_left(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
) -> list[Optional[bytes]]:
    """Return the parsed AccuWeather quartet for a partial cache miss."""
    return [
        accuweather_cached_location_key,
        accuweather_cached_current_conditions,
        None,
        None,
    ]


@pytest.fixture(name="accuweather_parsed_data_partial_hits_left")
def fixture_accuweather_parsed_data_partial_hits_left(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
) -> tuple[
    Optional[AccuweatherLocation],
    Optional[CurrentConditions],
    Optional[Forecast],
    Optional[int],
]:
    """Return the partial parsed AccuWeather triplet for a cache hit."""
    return (
        AccuweatherLocation.model_validate_json(accuweather_cached_location_key),
        CurrentConditions.model_validate_json(accuweather_cached_current_conditions),
        None,
        None,
    )


@pytest.fixture(name="accuweather_cached_data_partial_hits_right")
def fixture_accuweather_cached_data_partial_hits_right(
    accuweather_cached_location_key: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> list[Optional[bytes]]:
    """Return the parsed AccuWeather quartet for a partial cache miss."""
    return [
        accuweather_cached_location_key,
        None,
        accuweather_cached_forecast_fahrenheit,
        None,
    ]


@pytest.fixture(name="accuweather_parsed_data_partial_hits_right")
def fixture_accuweather_parsed_data_partial_hits_right(
    accuweather_cached_location_key: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> tuple[
    Optional[AccuweatherLocation],
    Optional[CurrentConditions],
    Optional[Forecast],
    Optional[int],
]:
    """Return the partial parsed AccuWeather quartet for a cache hit."""
    return (
        AccuweatherLocation.model_validate_json(accuweather_cached_location_key),
        None,
        Forecast.model_validate_json(accuweather_cached_forecast_fahrenheit),
        None,
    )


@pytest.fixture(name="accuweather_cached_data_misses")
def fixture_accuweather_cached_data_misses() -> list[Optional[bytes]]:
    """Return the cached AccuWeather quartet for a cache miss."""
    return [None, None, None, None]


@pytest.fixture(name="accuweather_parsed_data_misses")
def fixture_accuweather_parsed_data_misses() -> (
    tuple[
        Optional[AccuweatherLocation],
        Optional[CurrentConditions],
        Optional[Forecast],
        Optional[int],
    ]
):
    """Return the partial parsed AccuWeather quartet for a cache hit."""
    return (None, None, None, None)


def test_init_api_key_value_error(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any]
) -> None:
    """Test that a ValueError is raised if initializing with an empty API key."""
    expected_error_value: str = "AccuWeather API key not specified"
    accuweather_parameters["api_key"] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(
            cache=RedisAdapter(mocker.AsyncMock(spec=Redis)), **accuweather_parameters
        )

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    "url_value",
    [
        "url_param_api_key",
        "url_postalcodes_path",
        "url_postalcodes_param_query",
        "url_current_conditions_path",
        "url_forecasts_path",
    ],
)
def test_init_url_value_error(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any], url_value: str
) -> None:
    """Test that a ValueError is raised if initializing with empty URL values."""
    expected_error_value: str = (
        "One or more AccuWeather API URL parameters are undefined"
    )
    accuweather_parameters[url_value] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(
            cache=mocker.AsyncMock(spec=RedisAdapter), **accuweather_parameters
        )

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_weather_report(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    expected_weather_report: WeatherReport,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns a WeatherReport."""
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
    ]

    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report


@pytest.mark.asyncio
async def test_get_weather_report_from_cache(
    mocker: MockerFixture,
    geolocation: Location,
    statsd_mock: Any,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> None:
    """Test that we can get the weather report from cache."""
    redis_mock = mocker.AsyncMock(spec=Redis)

    async def script_callable(keys, args) -> list:
        return [
            accuweather_cached_location_key,
            accuweather_cached_current_conditions,
            accuweather_cached_forecast_fahrenheit,
            TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
        ]

    def mock_register_script(script) -> Callable[[list, list], Awaitable[list]]:
        return script_callable

    redis_mock.register_script.side_effect = mock_register_script

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report
    client_mock.get.assert_not_called()

    metrics_timeit_called = [
        call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert metrics_timeit_called == ["accuweather.cache.fetch"]

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == [
        "accuweather.cache.hit.locations",
        "accuweather.cache.hit.currentconditions",
        "accuweather.cache.hit.forecasts",
    ]


@pytest.mark.asyncio
async def test_get_weather_report_with_cache_fetch_error(
    mocker: MockerFixture,
    geolocation: Location,
    accuweather_parameters: dict[str, Any],
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that it should return None on the cache bulk fetch error."""
    caplog.set_level(logging.ERROR)

    redis_mock = mocker.AsyncMock(spec=Redis)

    async def script_callable(keys, args) -> list:
        raise RedisError("Failed to fetch")

    def mock_register_script(script) -> Callable[[list, list], Awaitable[list]]:
        return script_callable

    redis_mock.register_script.side_effect = mock_register_script

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None
    client_mock.get.assert_not_called()

    metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_called == ["accuweather.cache.fetch.error"]

    records = filter_caplog(
        caplog.records, "merino.providers.weather.backends.accuweather"
    )

    assert len(caplog.records) == 1
    assert records[0].message.startswith("Failed to fetch weather report from Redis:")


@pytest.mark.parametrize(
    "cached_current_fixture,cached_forecast_fixture,expected_http_call_count,"
    "expected_weather_report_ttl",
    [
        (None, None, 2, TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC),
        ("accuweather_cached_current_conditions", None, 1, TEST_CACHE_TTL_SEC),
        (None, "accuweather_cached_forecast_fahrenheit", 1, TEST_CACHE_TTL_SEC),
    ],
    ids=["missing-both", "missing-forecast", "missing-current-conditions"],
)
@pytest.mark.asyncio
async def test_get_weather_report_with_partial_cache_hits(
    request: FixtureRequest,
    mocker: MockerFixture,
    geolocation: Location,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    cached_current_fixture: Optional[str],
    cached_forecast_fixture: Optional[str],
    expected_http_call_count: int,
    expected_weather_report_ttl: int,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that we can get the weather report with partial cache hits."""
    cached_current_conditions = (
        request.getfixturevalue(cached_current_fixture)
        if cached_current_fixture
        else None
    )
    cached_forecast = (
        request.getfixturevalue(cached_forecast_fixture)
        if cached_forecast_fixture
        else None
    )

    redis_mock = mocker.AsyncMock(spec=Redis)

    async def mock_set(key, value, **kwargs) -> Any:
        return None

    async def script_callable(keys, args) -> list:
        return [
            accuweather_cached_location_key,
            cached_current_conditions,
            cached_forecast,
            None,
        ]

    def mock_register_script(script) -> Callable[[list, list], Awaitable[list]]:
        return script_callable

    redis_mock.register_script.side_effect = mock_register_script
    redis_mock.set.side_effect = mock_set

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    responses: list = []
    if cached_current_conditions is None:
        responses.append(
            Response(
                status_code=200,
                headers=response_header,
                content=accuweather_current_conditions_response,
                request=Request(
                    method="GET",
                    url=(
                        "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                        "apikey=test"
                    ),
                ),
            )
        )
    if cached_forecast is None:
        responses.append(
            Response(
                status_code=200,
                headers=response_header,
                content=accuweather_forecast_response_fahrenheit,
                request=Request(
                    method="GET",
                    url=(
                        "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                        "apikey=test"
                    ),
                ),
            )
        )

    # this only affects the first test run where both values are None.
    if cached_current_conditions is None and cached_forecast is None:
        mocker.patch(
            "merino.providers.weather.backends.accuweather.AccuweatherBackend"
            ".store_request_into_cache"
        ).return_value = TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    expected_weather_report.ttl = expected_weather_report_ttl
    assert report == expected_weather_report
    assert client_mock.get.call_count == expected_http_call_count


@pytest.mark.asyncio
async def test_get_weather_report_failed_location_query(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    postal code search query yields no result.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                "apikey=test&q=94105"
            ),
        ),
    )

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None


@pytest.mark.asyncio
async def test_get_weather_report_failed_current_conditions_query(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    current conditions query yields no result.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=b"[]",
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
    ]

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None


@pytest.mark.asyncio
async def test_get_weather_report_handles_exception_group_properly(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method raises an error if current condition call throws
    an error
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        HTTPError("Invalid Request - Current Conditions"),
        HTTPError("Invalid Request - Forecast"),
    ]
    expected_error_value: str = (
        "Failed to fetch weather report: ("
        "AccuweatherError('Unexpected current conditions response'), "
        "AccuweatherError('Unexpected forecast response')"
        ")"
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_weather_report(geolocation)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_weather_report_failed_forecast_query(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    forecast query yields no result.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=b"{}",
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                    "apikey=test"
                ),
            ),
        ),
    ]

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None


@pytest.mark.parametrize(
    "location",
    [
        Location(country="US", region="CA", city="San Francisco", dma=807),
        Location(region="CA", city="San Francisco", dma=807, postal_code="94105"),
    ],
    ids=["country", "postal_code"],
)
@pytest.mark.asyncio
async def test_get_weather_report_invalid_location(
    accuweather: AccuweatherBackend, location: Location
) -> None:
    """Test that the get_weather_report method raises an error if location information
    is missing.
    """
    expected_error_value: str = "Country and/or postal code unknown"

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_weather_report(location)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_location(
    accuweather: AccuweatherBackend,
    accuweather_location_response: bytes,
    response_header,
) -> None:
    """Test that the get_location method returns an AccuweatherLocation."""
    expected_location: AccuweatherLocation = AccuweatherLocation(
        key="39376_PC", localized_name="San Francisco"
    )
    country: str = "US"
    postal_code: str = "94105"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_location_response,
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                "apikey=test&q=94105"
            ),
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location(
        country, postal_code
    )

    assert location == expected_location


@pytest.mark.asyncio
async def test_get_location_no_location_returned(
    accuweather: AccuweatherBackend, response_header: dict[str, str]
) -> None:
    """Test that the get_location method returns None if the response content is not as
    expected.
    """
    country: str = "US"
    postal_code: str = "94105"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                "apikey=test&q=94105"
            ),
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location(
        country, postal_code
    )

    assert location is None


@pytest.mark.asyncio
async def test_get_location_error(accuweather: AccuweatherBackend) -> None:
    """Test that the get_location method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected location response"
    country: str = "US"
    postal_code: str = "94105"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=403,
        content=(
            b"{"
            b'"Code":"Unauthorized",'
            b'"Message":"Api Authorization failed",'
            b'"Reference":"/locations/v1/postalcodes/US/search.json?apikey=&details=true"'
            b"}"
        ),
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/locations/v1/postalcodes/US/search.json?"
                "apikey=test&q=94105"
            ),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location(country, postal_code)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_current_conditions_url"],
    [
        (
            "accuweather",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/"
            "39376_pc?lang=en-us",
        ),
    ],
    ids=["without_partner_code"],
)
@pytest.mark.asyncio
async def test_get_current_conditions(
    mocker: MockerFixture,
    request: FixtureRequest,
    accuweather_fixture: str,
    accuweather_current_conditions_response: bytes,
    expected_current_conditions_url: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_current_conditions method returns CurrentConditionsWithTTL."""
    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC

    expected_conditions: CurrentConditionsWithTTL = CurrentConditionsWithTTL(
        current_conditions=CurrentConditions(
            url=HttpUrl(expected_current_conditions_url),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60),
        ),
        ttl=TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )
    location_key: str = "39376_PC"
    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_current_conditions_response,
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                "apikey=test"
            ),
        ),
    )

    conditions: Optional[
        CurrentConditionsWithTTL
    ] = await accuweather.get_current_conditions(location_key)

    assert conditions == expected_conditions


@pytest.mark.asyncio
async def test_get_current_conditions_no_current_conditions_returned(
    accuweather: AccuweatherBackend, response_header: dict[str, str]
) -> None:
    """Test that the get_current_conditions method returns None if the response content
    is not as expected.
    """
    location_key: str = "39376_PC"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/currentconditions/v1/39376_PC.json?"
                "apikey=test"
            ),
        ),
    )

    conditions: Optional[
        CurrentConditionsWithTTL
    ] = await accuweather.get_current_conditions(location_key)

    assert conditions is None


@pytest.mark.asyncio
async def test_get_current_conditions_error(
    accuweather: AccuweatherBackend, response_header: dict[str, str]
) -> None:
    """Test that the get_current_conditions method raises an appropriate exception in
    the event of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected current conditions response"
    location_key: str = "INVALID"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=400,
        headers=response_header,
        content=(
            b"{"
            b"'Code':'400',"
            b"'Message':'Invalid location key: INVALID',"
            b"'Reference':'/currentconditions/v1/INVALID'"
            b"}"
        ),
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/currentconditions/v1/INVALID.json?"
                "apikey=test"
            ),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_current_conditions(location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_forecast_url"],
    [
        (
            "accuweather",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/daily-weather-forecast/"
            "39376_pc?lang=en-us",
        ),
    ],
    ids=["without_partner_code"],
)
@pytest.mark.parametrize(
    "forecast_response_fixture",
    [
        "accuweather_forecast_response_celsius",
        "accuweather_forecast_response_fahrenheit",
    ],
    ids=["celsius", "fahrenheit"],
)
@pytest.mark.asyncio
async def test_get_forecast(
    mocker: MockerFixture,
    request: FixtureRequest,
    accuweather_fixture: str,
    forecast_response_fixture: str,
    expected_forecast_url: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns a ForecastWithTTl."""
    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC

    expected_forecast: ForecastWithTTL = ForecastWithTTL(
        forecast=Forecast(
            url=HttpUrl(expected_forecast_url),
            summary="Pleasant Saturday",
            high=Temperature(f=70),
            low=Temperature(f=57),
        ),
        ttl=TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC,
    )

    location_key: str = "39376_PC"
    content: bytes = request.getfixturevalue(forecast_response_fixture)
    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=content,
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                "apikey=test"
            ),
        ),
    )

    forecast: Optional[ForecastWithTTL] = await accuweather.get_forecast(location_key)

    assert forecast == expected_forecast


@pytest.mark.asyncio
async def test_get_forecast_no_forecast_returned(
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns None if the response content is not as
    expected.
    """
    location_key: str = "39376_PC"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"{}",
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/forecasts/v1/daily/1day/39376_PC.json?"
                "apikey=test"
            ),
        ),
    )

    forecast: Optional[ForecastWithTTL] = await accuweather.get_forecast(location_key)

    assert forecast is None


@pytest.mark.asyncio
async def test_get_forecast_error(accuweather: AccuweatherBackend) -> None:
    """Test that the get_forecast method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected forecast response"
    location_key: str = "INVALID"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=400,
        content=(
            b"{"
            b"'Code':'400',"
            b"'Message':'Invalid location key: INVALID',"
            b"'Reference':'/forecasts/v1/daily/1day/INVALID.json'"
            b"}"
        ),
        request=Request(
            method="GET",
            url=(
                "http://www.accuweather.com/forecasts/v1/daily/1day/INVALID.json?"
                "apikey=test"
            ),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_forecast(location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ("query_params", "expected_cache_key"),
    [
        (
            {"q": "asdfg", "apikey": "filter_me_out"},
            f"AccuweatherBackend:v3:localhost:"
            f"{hashlib.blake2s('q'.encode('utf-8') + 'asdfg'.encode('utf-8')).hexdigest()}",
        ),
        (
            {},
            "AccuweatherBackend:v3:localhost",
        ),
        (
            {"q": "asdfg"},
            f"AccuweatherBackend:v3:localhost:"
            f"{hashlib.blake2s('q'.encode('utf-8') + 'asdfg'.encode('utf-8')).hexdigest()}",
        ),
    ],
    ids=["filter_out_apikey", "none", "pass_through_query"],
)
def test_cache_key_for_accuweather_request(
    accuweather: AccuweatherBackend,
    query_params: dict[str, str],
    expected_cache_key: str,
):
    """Test that the cache key is created properly."""
    url = "localhost"
    cache_key = accuweather.cache_key_for_accuweather_request(
        url, query_params=query_params
    )
    assert cache_key == expected_cache_key


@pytest.mark.parametrize(
    ("url", "expected_url_type"),
    [
        ("/forecasts/v1/daily/1day/39376_PC.json", "forecasts"),
        (
            "/currentconditions/v1/39376_PC.json",
            "currentconditions",
        ),
    ],
    ids=["cache_miss", "deserialization_error"],
)
@freezegun.freeze_time("2023-04-09")
@pytest.mark.asyncio
async def test_get_request_cache_get_errors(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    url: str,
    expected_url_type: str,
    statsd_mock: Any,
):
    """Test for cache errors/misses. Ensures that the right metrics are
    called and that the API request is actually made.
    """
    expiry_date = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
        days=2
    )
    expected_client_response = {"hello": "world", "cached_request_ttl": 0}

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=json.dumps(expected_client_response).encode("utf-8"),
        request=Request(
            method="GET",
            url=f"http://www.accuweather.com/{url}?apikey=test",
        ),
    )

    results: Optional[dict[str, Any]] = await accuweather.get_request(
        url,
        {"apikey": "test"},
        lambda a: cast(Optional[dict[str, Any]], a),
        TEST_CACHE_TTL_SEC,
    )

    assert expected_client_response == results

    timeit_metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert [
        f"accuweather.request.{expected_url_type}.get",
        "accuweather.cache.store",
    ] == timeit_metrics_called


@freezegun.freeze_time("2023-04-09")
@pytest.mark.asyncio
async def test_get_request_cache_store_errors(
    mocker: MockerFixture,
    accuweather_parameters: dict[str, Any],
    response_header: dict[str, str],
    statsd_mock: Any,
):
    """Test for cache errors/misses. Ensures that the right metrics are
    called and that the API request is actually made.
    """
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)
    url = "/forecasts/v1/daily/1day/39376_PC.json"

    redis_mock.get.side_effect = CacheMissError
    redis_mock.set.side_effect = CacheAdapterError(
        "Failed to set key with error: MockError"
    )

    expiry_date = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
        days=2
    )
    expected_client_response = {"hello": "world"}

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=redis_mock, **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=json.dumps(expected_client_response).encode("utf-8"),
        request=Request(
            method="GET",
            url=f"http://www.accuweather.com/{url}?apikey=test",
        ),
    )

    with pytest.raises(AccuweatherError):
        await accuweather.get_request(
            url,
            params={"apikey": "test"},
            process_api_response=lambda a: cast(Optional[dict[str, Any]], a),
            cache_ttl_sec=TEST_CACHE_TTL_SEC,
        )

    timeit_metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert [
        "accuweather.request.forecasts.get",
        "accuweather.cache.store",
    ] == timeit_metrics_called

    increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert [
        "accuweather.cache.store.set_error",
    ] == increment_called


@pytest.mark.asyncio
async def test_store_request_in_cache_error_invalid_expiry(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any]
):
    """Test that an error is raised for cache miss."""
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)

    accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)

    with pytest.raises(ValueError):
        await accuweather.store_request_into_cache(
            "key",
            {"hello": "cache"},
            "invalid_date_format",
            TEST_CACHE_TTL_SEC,
        )


@pytest.mark.parametrize(
    ("url", "partner_param_id", "partner_code", "expected_url"),
    [
        (
            "https://test.com",
            "partner",
            "test-partner",
            "https://test.com?partner=test-partner",
        ),
        ("https://test.com", None, None, "https://test.com"),
    ],
    ids=["", "missing_params"],
)
def test_add_partner_code(
    url: str,
    partner_param_id: Optional[str],
    partner_code: Optional[str],
    expected_url: str,
):
    """Test add_partner_code."""
    updated_url: str = add_partner_code(url, partner_param_id, partner_code)
    assert updated_url == expected_url


@pytest.mark.parametrize(
    ("cached_data", "expected_metrics"),
    [
        (
            ["location", "current", "forecast", "ttl"],
            ("hit.locations", "hit.currentconditions", "hit.forecasts"),
        ),
        (
            ["location", None, "forecast", "ttl"],
            ("hit.locations", "fetch.miss.currentconditions", "hit.forecasts"),
        ),
        (
            ["location", "current", None, "ttl"],
            ("hit.locations", "hit.currentconditions", "fetch.miss.forecasts"),
        ),
        (
            ["location", None, None, "ttl"],
            ("hit.locations", "fetch.miss.currentconditions", "fetch.miss.forecasts"),
        ),
        (
            [None, None, None, None],
            (
                "fetch.miss.locations",
                "fetch.miss.currentconditions",
                "fetch.miss.forecasts",
            ),
        ),
    ],
    ids=[
        "cache-hits",
        "partial-hits-left",
        "partial-hits-right",
        "partial-hits-one",
        "cache-misses",
    ],
)
def test_metrics_for_cache_fetch(
    accuweather: AccuweatherBackend,
    cached_data: list,
    expected_metrics: tuple,
    statsd_mock: Any,
):
    """Test metrics for cache fetches."""
    accuweather.emit_cache_fetch_metrics(cached_data)

    metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert [f"accuweather.cache.{val}" for val in expected_metrics] == metrics_called


@pytest.mark.parametrize(
    ("fixture_cached_data", "fixture_parsed_data"),
    [
        (
            "accuweather_cached_data_hits",
            "accuweather_parsed_data_hits",
        ),
        (
            "accuweather_cached_data_partial_hits",
            "accuweather_parsed_data_partial_hits",
        ),
        (
            "accuweather_cached_data_partial_hits_left",
            "accuweather_parsed_data_partial_hits_left",
        ),
        (
            "accuweather_cached_data_partial_hits_right",
            "accuweather_parsed_data_partial_hits_right",
        ),
        (
            "accuweather_cached_data_misses",
            "accuweather_parsed_data_misses",
        ),
    ],
    ids=[
        "cache-hits",
        "partial-hits",
        "partial-hits-left",
        "partial-hits-right",
        "cache-misses",
    ],
)
def test_parse_cached_data(
    request: FixtureRequest,
    accuweather: AccuweatherBackend,
    fixture_cached_data: str,
    fixture_parsed_data: str,
):
    """Test cached data parsing."""
    cached_data = request.getfixturevalue(fixture_cached_data)
    expected_parsed_data = request.getfixturevalue(fixture_parsed_data)

    res = accuweather.parse_cached_data(cached_data)

    assert res == expected_parsed_data


def test_parse_cached_data_error(
    accuweather: AccuweatherBackend,
    accuweather_cached_location_key: bytes,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
):
    """Test cached data parsing with errors."""
    caplog.set_level(logging.ERROR)

    location, current_conditions, forecast, ttl = accuweather.parse_cached_data(
        [
            accuweather_cached_location_key,
            b"invalid_current_condition",
            b"invalid_forecast",
            None,
        ]
    )

    assert location == AccuweatherLocation.model_validate_json(
        accuweather_cached_location_key
    )
    assert current_conditions is None
    assert forecast is None

    metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_called == ["accuweather.cache.data.error"]

    records = filter_caplog(
        caplog.records, "merino.providers.weather.backends.accuweather"
    )

    assert len(caplog.records) == 1
    assert records[0].message.startswith(
        "Failed to load weather report data from Redis:"
    )
