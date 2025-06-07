# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the AccuWeather backend module."""

import datetime
import json
import logging
from logging import ERROR, LogRecord
from typing import Any, Optional, cast, AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from pytest import LogCaptureFixture
import pytest_asyncio
from httpx import AsyncClient, Request, Response
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from redis.asyncio import Redis
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import AsyncRedisContainer

from tests.types import FilterCaplogFixture
from collections import namedtuple
from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError
from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.accuweather import (
    AccuweatherBackend,
    WeatherDataType,
)
from merino.providers.suggest.weather.backends.accuweather.errors import AccuweatherError
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
    WeatherContext,
)

ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
ACCUWEATHER_LOCATION_KEY = "39376"
ACCUWEATHER_METRICS_SAMPLE_RATE = 0.9

# these TTL values below are the same as the default accuweather config values
WEATHER_REPORT_TTL_SEC = 1800
CURRENT_CONDITIONS_TTL_SEC = 1800
FORECAST_TTL_SEC = 3600
LOCATION_KEY_TTL_SEC = 2592000

TEST_CACHE_ERROR = "test cache error"

CacheKeys = namedtuple("CacheKeys", ["location_key", "current_conditions_key", "forecast_key"])
logger = logging.getLogger(__name__)


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters(mocker: MockerFixture, statsd_mock: Any) -> dict[str, Any]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "cached_location_key_ttl_sec": LOCATION_KEY_TTL_SEC,
        "cached_current_condition_ttl_sec": CURRENT_CONDITIONS_TTL_SEC,
        "cached_forecast_ttl_sec": FORECAST_TTL_SEC,
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "url_param_api_key": "apikey",
        "url_cities_admin_path": "/locations/v1/cities/{country_code}/{admin_code}/search.json",
        "url_cities_path": "/locations/v1/cities/{country_code}/search.json",
        "url_cities_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
        "url_location_completion_path": "/locations/v1/cities/{country_code}/autocomplete.json",
        "url_location_key_placeholder": "{location_key}",
        "metrics_sample_rate": ACCUWEATHER_METRICS_SAMPLE_RATE,
    }


@pytest.fixture(name="expected_weather_report")
def fixture_expected_weather_report() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="San Francisco",
        region_code="CA",
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
        ttl=WEATHER_REPORT_TTL_SEC,
    )


@pytest.fixture(name="expected_weather_report_via_location_key")
def fixture_expected_weather_report_via_location_key() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="N/A",
        region_code="N/A",
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
        ttl=WEATHER_REPORT_TTL_SEC,
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


@pytest.fixture(name="weather_context_without_location_key")
def fixture_weather_context_without_location_key() -> WeatherContext:
    """Weather Context object for test."""
    return WeatherContext(
        Location(
            country="US",
            regions=["CA"],
            city="San Francisco",
            dma=807,
            postal_code="94105",
        ),
        ["en-US", "fr"],
    )


@pytest.fixture(name="weather_context_with_location_key")
def fixture_weather_context_with_location_key() -> WeatherContext:
    """Weather Context object for test."""
    return WeatherContext(
        Location(
            country="US",
            regions=["CA"],
            city="San Francisco",
            dma=807,
            postal_code="94105",
            key=ACCUWEATHER_LOCATION_KEY,
        ),
        ["en-US", "fr"],
    )


@pytest.fixture(name="accuweather_cached_location_key")
def fixture_accuweather_cached_location_key() -> bytes:
    """Return response content for AccuWeather city endpoint."""
    location: dict[str, Any] = {
        "key": "39376",
        "localized_name": "San Francisco",
        "administrative_area_id": "CA",
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


@pytest_asyncio.fixture(name="redis_client")
async def fixture_redis_client(
    redis_container: AsyncRedisContainer,
) -> AsyncGenerator[Redis, None]:
    """Create and return a Redis client"""
    client = await redis_container.get_async_client()

    yield client

    await client.flushall()


def generate_accuweather_cache_keys(
    accuweather: AccuweatherBackend,
    geolocation: Location,
    language: str | None,
) -> CacheKeys:
    """Generate cache keys for accuweather location, forecast and current conditions using
    accuweather backend class
    """
    # this is to satisfy mypy. The Location class defines all properties as optional,
    # however, the fixture we use has all properties set.
    assert geolocation.city is not None

    location_key: str = accuweather.cache_key_for_accuweather_request(
        accuweather.url_cities_admin_path.format(
            country_code=geolocation.country,
            admin_code=geolocation.regions[0] if geolocation.regions else None,
        ),
        query_params=accuweather.get_location_key_query_params(geolocation.city),
    )

    current_condition_cache_key: str = accuweather.cache_key_template(
        WeatherDataType.CURRENT_CONDITIONS,
        language,
    ).format(location_key=ACCUWEATHER_LOCATION_KEY)

    forecast_cache_key: str = accuweather.cache_key_template(
        WeatherDataType.FORECAST, language
    ).format(location_key=ACCUWEATHER_LOCATION_KEY)

    return CacheKeys(
        location_key=location_key,
        current_conditions_key=current_condition_cache_key,
        forecast_key=forecast_cache_key,
    )


async def set_redis_keys(redis_client: Redis, keys_and_values: list[tuple]) -> None:
    """Set redis cache keys and values after flushing the db"""
    for key, value, expiry in keys_and_values:
        await redis_client.set(key, value, ex=expiry)


@pytest.mark.asyncio
async def test_get_weather_report_from_cache_with_ttl(
    redis_client: Redis,
    weather_context_without_location_key: WeatherContext,
    statsd_mock: Any,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> None:
    """Test that we can get the weather report from cache with forecast and current conditions
    having a valid TTL
    """
    # set up the accuweather backend object with the testcontainer redis client
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    # get cache keys
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_without_location_key.geolocation,
        weather_context_without_location_key.languages[0],
    )

    # set the above keys with their values as their corresponding fixtures
    keys_values_expiry = [
        (cache_keys.location_key, accuweather_cached_location_key, LOCATION_KEY_TTL_SEC),
        (
            cache_keys.current_conditions_key,
            accuweather_cached_current_conditions,
            CURRENT_CONDITIONS_TTL_SEC,
        ),
        (cache_keys.forecast_key, accuweather_cached_forecast_fahrenheit, FORECAST_TTL_SEC),
    ]
    await set_redis_keys(redis_client, keys_values_expiry)

    # this http client mock isn't used to make any calls, but we do assert below on it not being
    # called
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_without_location_key
    )

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
    redis_client: Redis,
    weather_context_without_location_key: WeatherContext,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
) -> None:
    """Test that we can get the weather report with cache misses for both, current conditions
    and forecast
    """
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_without_location_key.geolocation,
        weather_context_without_location_key.languages[0],
    )

    await set_redis_keys(
        redis_client,
        [(cache_keys.location_key, accuweather_cached_location_key, LOCATION_KEY_TTL_SEC)],
    )
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
        weather_context_without_location_key
    )

    assert report == expected_weather_report
    assert client_mock.get.call_count == 2


@pytest.mark.asyncio
async def test_get_weather_report_with_only_current_conditions_cache_miss(
    redis_client: Redis,
    weather_context_without_location_key: WeatherContext,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> None:
    """Test that we can get weather report with only current conditions cache miss"""
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_without_location_key.geolocation,
        weather_context_without_location_key.languages[0],
    )

    keys_values_expiry = [
        (cache_keys.location_key, accuweather_cached_location_key, LOCATION_KEY_TTL_SEC),
        (cache_keys.forecast_key, accuweather_cached_forecast_fahrenheit, FORECAST_TTL_SEC),
    ]

    await set_redis_keys(redis_client, keys_values_expiry)

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
        weather_context_without_location_key
    )

    assert report == expected_weather_report
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_with_only_forecast_cache_miss(
    redis_client: Redis,
    weather_context_without_location_key: WeatherContext,
    expected_weather_report: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
) -> None:
    """Test that we can get weather report with only forecast cache miss"""
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_without_location_key.geolocation,
        weather_context_without_location_key.languages[0],
    )

    keys_values_expiry = [
        (cache_keys.location_key, accuweather_cached_location_key, LOCATION_KEY_TTL_SEC),
        (
            cache_keys.current_conditions_key,
            accuweather_cached_current_conditions,
            CURRENT_CONDITIONS_TTL_SEC,
        ),
    ]

    await set_redis_keys(redis_client, keys_values_expiry)

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
        weather_context_without_location_key
    )

    assert report == expected_weather_report
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_with_location_key_from_cache(
    redis_client: Redis,
    weather_context_with_location_key: WeatherContext,
    statsd_mock: Any,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> None:
    """Test that we can get the weather report from cache."""
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get cache keys, omitting the location key here
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_with_location_key.geolocation,
        weather_context_with_location_key.languages[0],
    )

    # set the above keys with their values as their corresponding fixtures
    keys_and_values = [
        (
            cache_keys.current_conditions_key,
            accuweather_cached_current_conditions,
            CURRENT_CONDITIONS_TTL_SEC,
        ),
        (cache_keys.forecast_key, accuweather_cached_forecast_fahrenheit, FORECAST_TTL_SEC),
    ]
    await set_redis_keys(redis_client, keys_and_values)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_with_location_key
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
    redis_client: Redis,
    weather_context_with_location_key: WeatherContext,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
) -> None:
    """Test that we can get weather report via location key with both current conditions and
    forecast cache miss
    """
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
        weather_context_with_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 2


@pytest.mark.asyncio
async def test_get_weather_report_via_location_key_with_only_current_conditions_cache_miss(
    redis_client: Redis,
    weather_context_with_location_key: WeatherContext,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_current_conditions_response: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> None:
    """Test that we can get weather report via location key with only current conditions cache
    miss
    """
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_with_location_key.geolocation,
        weather_context_with_location_key.languages[0],
    )

    keys_values_expiry = [
        (cache_keys.forecast_key, accuweather_cached_forecast_fahrenheit, FORECAST_TTL_SEC),
    ]

    await set_redis_keys(redis_client, keys_values_expiry)

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
        weather_context_with_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_via_location_key_with_only_forecast_cache_miss(
    redis_client: Redis,
    weather_context_with_location_key: WeatherContext,
    expected_weather_report_via_location_key: WeatherReport,
    accuweather_parameters: dict[str, Any],
    accuweather_forecast_response_fahrenheit: bytes,
    accuweather_cached_current_conditions: bytes,
) -> None:
    """Test that we can get weather report via location key with only forecast cache miss"""
    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    # get and set cache keys
    cache_keys = generate_accuweather_cache_keys(
        accuweather,
        weather_context_with_location_key.geolocation,
        weather_context_with_location_key.languages[0],
    )

    keys_values_expiry = [
        (
            cache_keys.current_conditions_key,
            accuweather_cached_current_conditions,
            CURRENT_CONDITIONS_TTL_SEC,
        ),
    ]

    await set_redis_keys(redis_client, keys_values_expiry)

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
        weather_context_with_location_key
    )

    assert report == expected_weather_report_via_location_key
    assert client_mock.get.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_report_with_location_key_with_cache_error(
    redis_client: Redis,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    weather_context_with_location_key: WeatherContext,
    statsd_mock: Any,
    accuweather_parameters: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    """Test that we catch the CacheAdapterError exception and raise an `AccuweatherError`
    when running the script against the cache.
    """
    caplog.set_level(ERROR)

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_client), **accuweather_parameters
    )
    redis_error_mock = mocker.patch.object(accuweather.cache, "run_script", new_callable=AsyncMock)
    redis_error_mock.side_effect = CacheAdapterError(TEST_CACHE_ERROR)

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    with pytest.raises(AccuweatherError):
        _ = await accuweather.get_weather_report(weather_context_with_location_key)

    records: list[LogRecord] = filter_caplog(
        caplog.records, "merino.providers.suggest.weather.backends.accuweather.backend"
    )

    client_mock.get.assert_not_called()

    assert len(records) == 1
    assert records[0].message.startswith(
        f"Failed to fetch weather report from Redis: {TEST_CACHE_ERROR}"
    )

    metrics_timeit_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_timeit_called == ["accuweather.cache.fetch-via-location-key"]

    metrics_increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert metrics_increment_called == [
        "accuweather.cache.fetch-via-location-key.error",
    ]
