# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the AccuWeather backend module."""

import datetime
import json
import logging
from typing import Any, Optional, cast
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Request, Response
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from merino.cache.redis import RedisAdapter
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.accuweather import (
    AccuweatherBackend,
    WeatherDataType,
)
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)

ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
TEST_CACHE_TTL_SEC = 1800

logger = logging.getLogger(__name__)


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters(mocker: MockerFixture, statsd_mock: Any) -> dict[str, Any]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "cached_location_key_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_current_condition_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_forecast_ttl_sec": TEST_CACHE_TTL_SEC,
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "url_param_api_key": "apikey",
        "url_cities_path": "/locations/v1/cities/{country_code}/{admin_code}/search.json",
        "url_cities_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
        "url_location_completion_path": "/locations/v1/cities/{country_code}/autocomplete.json",
        "url_location_key_placeholder": "{location_key}",
    }


@pytest.fixture(name="accuweather_location_key")
def fixture_accuweather_location_key() -> str:
    """Location key for the expected weather report."""
    return "39376"


@pytest.fixture(name="expected_weather_report")
def fixture_expected_weather_report() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
        ttl=TEST_CACHE_TTL_SEC,
    )


@pytest.fixture(name="expected_weather_report_via_location_key")
def fixture_expected_weather_report_via_location_key() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="N/A",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
        ttl=TEST_CACHE_TTL_SEC,
    )


@pytest.fixture(name="accuweather_location_completion_response")
def fixture_accuweather_location_completion_response(
    location_completion_sample_cities,
) -> bytes:
    """Return response content for AccuWeather location autocomplete endpoint."""
    return json.dumps(location_completion_sample_cities).encode("utf-8")


@pytest.fixture(name="response_header")
def fixture_response_header() -> dict[str, str]:
    """Create a response header with a reasonable expiry."""
    expiry_time: datetime.datetime = datetime.datetime.now(
        tz=datetime.timezone.utc
    ) + datetime.timedelta(days=2)
    return {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Create a Location object for test."""
    return Location(country="US", region="CA", city="San Francisco", dma=807, postal_code="94105")


@pytest.fixture(name="accuweather_cached_location_key")
def fixture_accuweather_cached_location_key() -> bytes:
    """Return response content for AccuWeather city endpoint."""
    location: dict[str, Any] = {
        "key": "39376",
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
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us"
            ),
            "Link": (
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us"
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
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us"
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
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376?lang=en-us"
            ),
            "Link": (
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376?lang=en-us"
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
                    "https://www.accuweather.com/en/us/san-francisco-ca/"
                    "94103/daily-weather-forecast/39376?day=1&lang=en-us"
                ),
                "Link": (
                    "https://www.accuweather.com/en/us/san-francisco-ca/"
                    "94103/daily-weather-forecast/39376?day=1&lang=en-us"
                ),
            }
        ],
    }


@pytest.fixture(name="accuweather_forecast_response_fahrenheit")
def fixture_accuweather_forecast_response_fahrenheit(
    accuweather_forecast_response: dict[str, Any],
) -> bytes:
    """Return response content for AccuWeather forecast endpoint in fahrenheit."""
    accuweather_forecast_response["DailyForecasts"][0]["Temperature"] = {
        "Minimum": {"Value": 57.0, "Unit": "F", "UnitType": 18},
        "Maximum": {"Value": 70.0, "Unit": "F", "UnitType": 18},
    }
    return json.dumps(accuweather_forecast_response).encode("utf-8")


@pytest.fixture(name="accuweather_cached_forecast_fahrenheit")
def fixture_accuweather_cached_forecast_fahrenheit() -> bytes:
    """Return the cached AccuWeather forecast in Fahrenheit."""
    return json.dumps(
        {
            "url": (
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376?lang=en-us"
            ),
            "summary": "Pleasant Saturday",
            "high": {"f": 70.0},
            "low": {"f": 57.0},
        }
    ).encode("utf-8")


@pytest.fixture(scope="module")
def redis_container() -> AsyncRedisContainer:
    """Create and return a docker container for Redis. Tear it down after all the tests have
    finished running
    """
    logger.info("Starting up redis container")
    container = AsyncRedisContainer().start()

    # wait for the container to start and emit logs
    delay = wait_for_logs(container, "Server initialized")
    logger.info(f"\n Redis server started with delay: {delay} seconds on port: {container.port}")

    yield container

    container.stop()
    logger.info("\n Redis container stopped")


def generate_accuweather_cache_keys(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_key: str,
) -> list[str]:
    """Generate cache keys for accuweather location, forecast and current conditions using
    accuweather backend class
    """
    # this is to satisfy mypy. The Location class defines all properties as optional,
    # however, the fixture we use has all properties set.
    assert geolocation.city is not None

    location_key: str = accuweather.cache_key_for_accuweather_request(
        accuweather.url_cities_path.format(
            country_code=geolocation.country, admin_code=geolocation.region
        ),
        query_params=accuweather.get_location_key_query_params(geolocation.city),
    )

    current_condition_cache_key: str = accuweather.cache_key_template(
        WeatherDataType.CURRENT_CONDITIONS
    ).format(location_key=accuweather_location_key)

    forecast_cache_key: str = accuweather.cache_key_template(WeatherDataType.FORECAST).format(
        location_key=accuweather_location_key
    )

    return [location_key, current_condition_cache_key, forecast_cache_key]


async def set_redis_keys(redis_client: Redis, keys_and_values: list[tuple]) -> None:
    """Set redis cache keys and values after flushing the db"""
    await redis_client.flushall()
    for key, value in keys_and_values:
        await redis_client.set(key, value)


@pytest.mark.asyncio
async def test_get_weather_report_from_cache(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    statsd_mock: Any,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get the weather report from cache."""
    redis_client = await redis_container.get_async_client()

    # set up the accuweather backend object with the testcontainer redis client
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    # get cache keys
    location_key, current_condition_cache_key, forecast_cache_key = (
        generate_accuweather_cache_keys(accuweather, geolocation, accuweather_location_key)
    )

    # set the above keys with their values as their corresponding fixtures
    keys_and_values = [
        (location_key, accuweather_cached_location_key),
        (current_condition_cache_key, accuweather_cached_current_conditions),
        (forecast_cache_key, accuweather_cached_forecast_fahrenheit),
    ]
    await set_redis_keys(redis_client, keys_and_values)

    # this http client mock isn't used to make any calls, but we do assert below on it not being
    # called
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report
    client_mock.get.assert_not_called()

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
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
async def test_get_weather_report_with_both_current_conditions_and_forecast_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get the weather report with cache misses for both, current conditions
    and forecast
    """
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    location_key, _, _ = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    await set_redis_keys(redis_client, [(location_key, accuweather_cached_location_key)])
    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("https://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report
    assert client_mock.get.call_count == 2


@pytest.mark.asyncio
async def test_get_weather_report_with_only_current_conditions_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get weather report with only current conditions cache miss"""
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    location_cache_key, _, forecast_cache_key = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    cache_keys_values = [
        (location_cache_key, accuweather_cached_location_key),
        (forecast_cache_key, accuweather_cached_forecast_fahrenheit),
    ]

    await set_redis_keys(redis_client, cache_keys_values)

    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("https://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        )
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_with_only_forecast_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get weather report with only forecast cache miss"""
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    location_cache_key, current_conditions_cache_key, _ = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    cache_keys_values = [
        (location_cache_key, accuweather_cached_location_key),
        (current_conditions_cache_key, accuweather_cached_current_conditions),
    ]

    await set_redis_keys(redis_client, cache_keys_values)

    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        )
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_weather_report
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_with_location_key_from_cache(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    statsd_mock: Any,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get the weather report from cache."""
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get cache keys, omitting the location key here
    _, current_condition_cache_key, forecast_cache_key = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    # set the above keys with their values as their corresponding fixtures
    keys_and_values = [
        (current_condition_cache_key, accuweather_cached_current_conditions),
        (forecast_cache_key, accuweather_cached_forecast_fahrenheit),
    ]
    await set_redis_keys(redis_client, keys_and_values)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        geolocation, accuweather_location_key
    )
    assert report == expected_weather_report_via_location_key
    client_mock.get.assert_not_called()

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == ["accuweather.cache.fetch-via-location-key"]

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]

    assert metrics_increment_called == [
        "accuweather.cache.hit.currentconditions",
        "accuweather.cache.hit.forecasts",
    ]


@pytest.mark.asyncio
async def test_get_weather_report_via_location_key_with_both_current_conditions_and_forecast_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get weather report via location key with both current conditionsand
    forecast cache miss
    """
    redis_client = await redis_container.get_async_client()
    await redis_client.flushall()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("https://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        geolocation, accuweather_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 2


@pytest.mark.asyncio
async def test_get_weather_report_via_location_key_with_only_current_conditions_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get weather report via location key with only current conditions cache
    miss
    """
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    _, _, forecast_cache_key = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    cache_keys_values = [
        (forecast_cache_key, accuweather_cached_forecast_fahrenheit),
    ]

    await set_redis_keys(redis_client, cache_keys_values)

    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("https://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        )
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        geolocation, accuweather_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_via_location_key_with_only_forecast_cache_miss(
    redis_container: AsyncRedisContainer,
    geolocation: Location,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_forecast_response_fahrenheit: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_location_key: str,
) -> None:
    """Test that we can get weather report via location key with only forecast cache miss"""
    redis_client = await redis_container.get_async_client()

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    _, current_conditions_cache_key, _ = generate_accuweather_cache_keys(
        accuweather, geolocation, accuweather_location_key
    )

    cache_keys_values = [
        (current_conditions_cache_key, accuweather_cached_current_conditions),
    ]

    await set_redis_keys(redis_client, cache_keys_values)

    # generating a datetime of now to resemble source code and set it as the 'Expiry' response
    # header
    expiry_time = datetime.datetime.now(tz=datetime.timezone.utc)
    resp_header = {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}

    responses: list = [
        Response(
            status_code=200,
            headers=resp_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        )
    ]

    client_mock.get.side_effect = responses
    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        geolocation, accuweather_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 1
