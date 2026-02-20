# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AccuWeather backend module."""

import datetime
import hashlib
from dataclasses import replace

import orjson
import logging
from ssl import SSLError
from typing import Any, Awaitable, Callable, Optional, cast
from unittest.mock import AsyncMock

import pytest
import freezegun
from httpx import AsyncClient, HTTPError, Request, Response
from pydantic import HttpUrl
from pytest import FixtureRequest, LogCaptureFixture
from pytest_mock import MockerFixture
from redis import RedisError
from redis.asyncio import Redis

from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError, CacheMissError
from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.accuweather import (
    AccuweatherBackend,
    AccuweatherError,
    AccuweatherLocation,
    CurrentConditionsWithTTL,
    ForecastWithTTL,
)
from merino.providers.suggest.weather.backends.accuweather.errors import (
    AccuweatherErrorMessages,
    MissingLocationKeyError,
)
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    clear_skip_cities_mapping,
    increment_skip_cities_mapping,
    get_skip_cities_mapping,
)
from merino.providers.suggest.weather.backends.accuweather.utils import (
    RequestType,
    add_partner_code,
    get_language,
    process_hourly_forecast_response,
    update_weather_url_with_suggest_partner_code,
)
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    HourlyForecastsWithTTL,
    LocationCompletion,
    LocationCompletionGeoDetails,
    Temperature,
    WeatherReport,
    WeatherContext,
)
from tests.types import FilterCaplogFixture

ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
TEST_CACHE_TTL_SEC = 1800
TEST_DEFAULT_WEATHER_REPORT_CACHE_TTL_SEC = 300
TEST_HOURLY_FORECASTS_CACHE_TTL_SEC = 3600
ACCUWEATHER_METRICS_SAMPLE_RATE = 0.9


@pytest.fixture(name="redis_mock_cache_miss")
def fixture_redis_mock_cache_miss(mocker: MockerFixture) -> Any:
    """Create a Redis client mock object for testing."""

    async def mock_get(key) -> Any:
        return None

    async def mock_set(key, value, **kwargs) -> Any:
        return None

    async def script_callable(keys, args, readonly) -> list:
        return []

    def mock_register_script(script) -> Callable[[list, list, bool], Awaitable[list]]:
        return script_callable

    mock = mocker.AsyncMock(spec=Redis)
    mock.get.side_effect = mock_get
    mock.set.side_effect = mock_set
    mock.register_script.side_effect = mock_register_script
    return mock


@pytest.fixture(name="location_response_for_fallback")
def fixture_location_response_for_fallback() -> bytes:
    """Create a fixture for location response for fallback."""
    return orjson.dumps(
        [
            {
                "Version": 1,
                "Key": "39376",
                "Type": "City",
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
            },
        ]
    )


@pytest.fixture(name="location_completion_sample_cities")
def fixture_location_completion_sample_cities() -> list[dict[str, Any]]:
    """Create a list of sample location completions for the search term 'new'"""
    return [
        {
            "Version": 1,
            "Key": "349727",
            "Type": "City",
            "Rank": 15,
            "LocalizedName": "New York",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NY", "LocalizedName": "New York"},
        },
        {
            "Version": 1,
            "Key": "348585",
            "Type": "City",
            "Rank": 35,
            "LocalizedName": "New Orleans",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "LA", "LocalizedName": "Louisiana"},
        },
        {
            "Version": 1,
            "Key": "349530",
            "Type": "City",
            "Rank": 35,
            "LocalizedName": "Newark",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NJ", "LocalizedName": "New Jersey"},
        },
        {
            "Version": 1,
            "Key": "331967",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newport Beach",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "CA", "LocalizedName": "California"},
        },
        {
            "Version": 1,
            "Key": "327357",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Haven",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "CT", "LocalizedName": "Connecticut"},
        },
        {
            "Version": 1,
            "Key": "333575",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Bedford",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "MA", "LocalizedName": "Massachusetts"},
        },
        {
            "Version": 1,
            "Key": "338640",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newton",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "MA", "LocalizedName": "Massachusetts"},
        },
        {
            "Version": 1,
            "Key": "339713",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Rochelle",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NY", "LocalizedName": "New York"},
        },
        {
            "Version": 1,
            "Key": "336210",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newport News",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "VA", "LocalizedName": "Virginia"},
        },
        {
            "Version": 1,
            "Key": "2626691",
            "Type": "City",
            "Rank": 55,
            "LocalizedName": "Near Eastside",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "IN", "LocalizedName": "Indiana"},
        },
    ]


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters(mocker: MockerFixture, statsd_mock: Any) -> dict[str, Any]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "cached_location_key_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_current_condition_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_forecast_ttl_sec": TEST_CACHE_TTL_SEC,
        "cached_hourly_forecast_ttl_sec": TEST_CACHE_TTL_SEC,
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "url_param_api_key": "apikey",
        "url_cities_admin_path": "/locations/v1/cities/{country_code}/{admin_code}/search.json",
        "url_cities_path": "locations/v1/cities/{country_code}/search.json",
        "url_cities_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
        "url_hourly_forecasts_path": "/forecasts/v1/hourly/12hour/{location_key}.json",
        "url_location_completion_path": "/locations/v1/cities/{country_code}/autocomplete.json",
        "url_location_key_placeholder": "{location_key}",
        "metrics_sample_rate": ACCUWEATHER_METRICS_SAMPLE_RATE,
    }


@pytest.fixture(name="accuweather_location_key")
def fixture_accuweather_location_key() -> str:
    """Location key for the expected weather report."""
    return "39376"


@pytest.fixture(name="languages")
def fixture_languages() -> list[str]:
    """Language list to get weather report."""
    return ["en-US", "fr"]


@pytest.fixture(name="language")
def fixture_language() -> str:
    """Language list to get weather report."""
    return "en-US"


@pytest.fixture(name="weather_context_with_location_key")
def fixture_weather_context_with_location_key() -> WeatherContext:
    """Weather Context Object with location key for tests."""
    return WeatherContext(
        Location(
            country="US",
            regions=["CA", "BC"],
            city="San Francisco",
            dma=807,
            postal_code="94105",
            key="39376",
        ),
        ["en-US", "fr"],
    )


@pytest.fixture(name="weather_context_without_location_key")
def fixture_weather_context_without_location_key() -> WeatherContext:
    """Weather Context Object with location key for tests."""
    return WeatherContext(
        Location(
            country="US",
            regions=["CA", "BC"],
            city="San Francisco",
            dma=807,
            postal_code="94105",
            city_names={"en": "San Francisco", "fr": "Sân Frâncisco", "es": "Sán Fráncisco"},
        ),
        ["en-US", "fr", "es"],
    )


@pytest.fixture(name="expected_weather_report")
def fixture_expected_weather_report() -> WeatherReport:
    """Create an `AccuWeatherReport` for assertions"""
    return WeatherReport(
        city_name="San Francisco",
        region_code="United States",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376?lang=en-us&partner=test_newtab"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376?lang=en-us&partner=test_newtab"
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
        region_code="N/A",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376?lang=en-us&partner=test_newtab"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
                "https://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376?lang=en-us&partner=test_newtab"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
        ttl=TEST_CACHE_TTL_SEC,
    )


@pytest.fixture(name="expected_location_completion")
def fixture_expected_location_completion(
    location_completion_sample_cities,
) -> list[LocationCompletion]:
    """Create a `LocationCompletion` list for assertions"""
    return [
        LocationCompletion(
            key=location["Key"],
            rank=location["Rank"],
            type=location["Type"],
            localized_name=location["LocalizedName"],
            country=LocationCompletionGeoDetails(
                id=location["Country"]["ID"],
                localized_name=location["Country"]["LocalizedName"],
            ),
            administrative_area=LocationCompletionGeoDetails(
                id=location["AdministrativeArea"]["ID"],
                localized_name=location["AdministrativeArea"]["LocalizedName"],
            ),
        )
        for location in location_completion_sample_cities
    ]


@pytest.fixture(name="accuweather_location_completion_response")
def fixture_accuweather_location_completion_response(
    location_completion_sample_cities,
) -> bytes:
    """Return response content for AccuWeather location autocomplete endpoint."""
    return orjson.dumps(location_completion_sample_cities)


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
        country="US",
        regions=["CA", "BC"],
        city="San Francisco",
        dma=807,
        postal_code="94105",
    )


@pytest.fixture(name="accuweather_location_response")
def fixture_accuweather_location_response() -> bytes:
    """Return response content for AccuWeather cities endpoint."""
    response: list[dict[str, Any]] = [
        {
            "Version": 1,
            "Key": "39376",
            "Type": "City",
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
        },
        {
            "Version": 2,
            "Key": "888888",
            "Type": "City",
            "Rank": 135,
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
        },
    ]
    return orjson.dumps(response)


@pytest.fixture(name="accuweather_cached_location_key")
def fixture_accuweather_cached_location_key() -> bytes:
    """Return response content for AccuWeather city endpoint."""
    location: dict[str, Any] = {
        "key": "39376",
        "localized_name": "San Francisco",
        "administrative_area_id": "CA",
        "country_name": "United States",
    }
    return orjson.dumps(location)


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
    return orjson.dumps(response)


@pytest.fixture(name="accuweather_cached_current_conditions")
def fixture_accuweather_cached_current_conditions() -> bytes:
    """Return the cached content for AccuWeather current conditions."""
    return orjson.dumps(
        {
            "url": (
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376?lang=en-us&partner=test_newtab"
            ),
            "summary": "Mostly cloudy",
            "icon_id": 6,
            "temperature": {"c": 15.5, "f": 60.0},
        }
    )


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


@pytest.fixture(name="accuweather_forecast_response_celsius")
def fixture_accuweather_forecast_response_celsius(
    accuweather_forecast_response: dict[str, Any],
) -> bytes:
    """Return response content for AccuWeather forecast endpoint in celsius."""
    accuweather_forecast_response["DailyForecasts"][0]["Temperature"] = {
        "Minimum": {"Value": 13.9, "Unit": "C", "UnitType": 17},
        "Maximum": {"Value": 21.1, "Unit": "C", "UnitType": 17},
    }
    return orjson.dumps(accuweather_forecast_response)


@pytest.fixture(name="accuweather_forecast_response_fahrenheit")
def fixture_accuweather_forecast_response_fahrenheit(
    accuweather_forecast_response: dict[str, Any],
) -> bytes:
    """Return response content for AccuWeather forecast endpoint in fahrenheit."""
    accuweather_forecast_response["DailyForecasts"][0]["Temperature"] = {
        "Minimum": {"Value": 57.0, "Unit": "F", "UnitType": 18},
        "Maximum": {"Value": 70.0, "Unit": "F", "UnitType": 18},
    }
    return orjson.dumps(accuweather_forecast_response)


@pytest.fixture(name="accuweather_cached_forecast_fahrenheit")
def fixture_accuweather_cached_forecast_fahrenheit() -> bytes:
    """Return the cached AccuWeather forecast in fahrenheit."""
    return orjson.dumps(
        {
            "url": (
                "https://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376?lang=en-us"
            ),
            "summary": "Pleasant Saturday",
            "high": {"f": 70.0},
            "low": {"f": 57.0},
        }
    )


@pytest.fixture(name="accuweather_hourly_forecast_response")
def fixture_accuweather_hourly_forecast_response() -> bytes:
    """AccuWeather API response with 12 hourly forecasts."""
    forecasts = []
    base_time = 1708281600  # Example epoch time

    for i in range(12):
        hour = 14 + i
        forecasts.append(
            {
                "DateTime": f"2026-02-18T{hour:02d}:00:00-05:00",
                "EpochDateTime": base_time + (i * 3600),
                "Temperature": {"Unit": "F", "Value": 60 + i},
                "WeatherIcon": 6,
                "Link": f"http://www.accuweather.com/en/us/san-francisco/94105/hourly-weather-forecast/39376?day=1&hbhhour={hour}&lang=en-us",
            }
        )

    return orjson.dumps(forecasts)


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
    """Return the parsed AccuWeather triplet for a cache hit."""
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
def fixture_accuweather_cached_data_partial_hits_left(
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


@pytest.fixture(name="accuweather_cached_data_partial_miss_ttl")
def fixture_accuweather_cached_data_partial_miss_ttl(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> list[Optional[bytes] | Optional[int]]:
    """Return the cached AccuWeather quartet for a cache hit but a TTL miss"""
    return [
        accuweather_cached_location_key,
        accuweather_cached_current_conditions,
        accuweather_cached_forecast_fahrenheit,
        None,
    ]


@pytest.fixture(name="accuweather_parsed_data_partial_miss_ttl")
def fixture_accuweather_parsed_data_partial_miss_ttl(
    accuweather_cached_location_key: bytes,
    accuweather_cached_current_conditions: bytes,
    accuweather_cached_forecast_fahrenheit: bytes,
) -> tuple[
    Optional[AccuweatherLocation],
    Optional[CurrentConditions],
    Optional[Forecast],
    Optional[int],
]:
    """Return the parsed AccuWeather triplet for a cache hit but a TTL miss"""
    return (
        AccuweatherLocation.model_validate_json(accuweather_cached_location_key),
        CurrentConditions.model_validate_json(accuweather_cached_current_conditions),
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


@pytest.fixture(autouse=True)
def run_before_each_test():
    """Clear SKIP_CITIES_MAPPING."""
    clear_skip_cities_mapping()


def test_init_api_key_value_error(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any]
) -> None:
    """Test that a ValueError is raised if initializing with an empty API key."""
    expected_error_value: str = "AccuWeather API key not specified"
    accuweather_parameters["api_key"] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(
            cache=RedisAdapter(mocker.AsyncMock(spec=Redis)),
            **accuweather_parameters,
        )

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    "url_value",
    [
        "url_param_api_key",
        "url_cities_path",
        "url_cities_param_query",
        "url_current_conditions_path",
        "url_forecasts_path",
    ],
)
def test_init_url_value_error(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any], url_value: str
) -> None:
    """Test that a ValueError is raised if initializing with empty URL values."""
    expected_error_value: str = "One or more AccuWeather API URL parameters are undefined"
    accuweather_parameters[url_value] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(cache=mocker.AsyncMock(spec=RedisAdapter), **accuweather_parameters)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_weather_report(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    expected_weather_report: WeatherReport,
    weather_context_without_location_key: WeatherContext,
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
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
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
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_CACHE_TTL_SEC

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_without_location_key
    )

    assert report == expected_weather_report


@pytest.mark.asyncio
async def test_get_weather_report_without_region(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    expected_weather_report: WeatherReport,
    weather_context_without_location_key: WeatherContext,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
    location_response_for_fallback: bytes,
) -> None:
    """Test that the get_weather_report method returns a WeatherReport even without a valid region."""
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=location_response_for_fallback,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
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
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_CACHE_TTL_SEC
    geolocation = weather_context_without_location_key.geolocation
    geolocation = geolocation.model_copy()
    geolocation.regions = None
    weather_context_without_location_key.geolocation = geolocation
    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_without_location_key
    )

    assert report == expected_weather_report


@pytest.mark.asyncio
async def test_get_weather_report_with_fallback_city_endpoint_returns_none(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
    expected_weather_report: WeatherReport,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that the get_weather_report method returns nothing when multiple locations in response."""
    caplog.set_level(logging.WARN)

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=b"[]",
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                    "apikey=test&q=SanFrancisco"
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
                    "https://www.accuweather.com/locations/v1/cities/US/BC/search.json?"
                    "apikey=test&q=SanFrancisco"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/locations/v1/cities/US/search.json?"
                    "apikey=test&q=SanFrancisco"
                ),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_CACHE_TTL_SEC

    with pytest.raises(MissingLocationKeyError):
        await accuweather.get_weather_report(weather_context_without_location_key)

        assert len(get_skip_cities_mapping()) == 1


@pytest.mark.asyncio
async def test_get_weather_report_location_key_fetch_failed(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    response_header: dict[str, str],
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that the get_weather_report method returns a WeatherReport using alternate region."""
    caplog.set_level(logging.WARN)

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=403,
            content=(
                b"{"
                b'"Code":"Unauthorized",'
                b'"Message":"Api Authorization failed",'
                b'"Reference":"/locations/v1/cities/US/CA/search.json?apikey=&details=true"'
                b"}"
            ),
            headers=response_header,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                    "apikey=test&q=SanFrancisco"
                ),
            ),
        ),
    ]

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_without_location_key
    )

    assert report is None

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.weather.backends.accuweather.backend"
    )

    assert len(caplog.records) == 1

    assert records[0].message.startswith("Unexpected location response from")


@pytest.mark.asyncio
async def test_get_weather_report_with_location_key(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    expected_weather_report_via_location_key: WeatherReport,
    weather_context_with_location_key: WeatherContext,
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
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_CACHE_TTL_SEC
    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_with_location_key
    )

    assert report == expected_weather_report_via_location_key


@pytest.mark.asyncio
async def test_get_weather_report_with_cache_fetch_error(
    mocker: MockerFixture,
    weather_context_without_location_key: WeatherContext,
    accuweather_parameters: dict[str, Any],
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that it should raise an exception on the cache bulk fetch error."""
    caplog.set_level(logging.ERROR)

    redis_mock = mocker.AsyncMock(spec=Redis)

    async def script_callable(keys, args, readonly) -> list:
        raise RedisError("Failed to fetch")

    def mock_register_script(script) -> Callable[[list, list, bool], Awaitable[list]]:
        return script_callable

    redis_mock.register_script.side_effect = mock_register_script

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    with pytest.raises(AccuweatherError):
        _ = await accuweather.get_weather_report(weather_context_without_location_key)

    client_mock.get.assert_not_called()

    metrics_called = [call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list]
    assert metrics_called == ["accuweather.cache.fetch.error"]

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.weather.backends.accuweather.backend"
    )

    assert len(caplog.records) == 1
    assert records[0].message.startswith("Failed to fetch weather report from Redis:")


@pytest.mark.asyncio
async def test_get_weather_report_failed_location_query(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    city search query yields no result.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=(
                "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                "apikey=test&q=94105"
            ),
        ),
    )

    with pytest.raises(MissingLocationKeyError):
        await accuweather.get_weather_report(weather_context_without_location_key)


@pytest.mark.asyncio
async def test_get_weather_report_failed_current_conditions_query(
    accuweather: AccuweatherBackend,
    weather_context_with_location_key: WeatherContext,
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
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
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
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_with_location_key
    )

    assert report is None


@pytest.mark.asyncio
async def test_get_weather_report_handles_exception_group_properly(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
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
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        HTTPError("Invalid Request - Current Conditions"),
        HTTPError("Invalid Request - Forecast"),
    ]
    expected_error_value: str = (
        "Failed to fetch weather report: ("
        "AccuweatherError('Unexpected current conditions response, Url: /currentconditions/v1/39376.json'), "
        "AccuweatherError('Unexpected forecast response, Url: /forecasts/v1/daily/1day/39376.json')"
        ")"
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_weather_report(weather_context_without_location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_weather_report_handles_non_http_exception_group_properly(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    accuweather_location_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method raises an AccuweatherError if the current
    conditions and forecast calls raise an error
    """
    # we are specifically raising SSLError and ValueError which should be caught by the
    # generic Exception catch block in the respective function calls
    current_conditions_error = SSLError("current conditions")
    forecast_error = ValueError("forecast")

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url=(
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                    "apikey=test&q=94105"
                ),
            ),
        ),
        current_conditions_error,
        forecast_error,
    ]
    accuweather_error_for_current_conditions = AccuweatherError(
        AccuweatherErrorMessages.UNEXPECTED_CURRENT_CONDITIONS_ERROR,
        exception_class_name=current_conditions_error.__class__.__name__,
    )
    accuweather_error_for_forecast = AccuweatherError(
        AccuweatherErrorMessages.UNEXPECTED_FORECAST_ERROR,
        exception_class_name=forecast_error.__class__.__name__,
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_weather_report(weather_context_without_location_key)

    assert str(accuweather_error_for_current_conditions) in str(accuweather_error.value)
    assert str(accuweather_error_for_forecast) in str(accuweather_error.value)


@pytest.mark.asyncio
async def test_get_weather_report_failed_forecast_query(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
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
                    "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
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
                url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=b"{}",
            request=Request(
                method="GET",
                url=(
                    "http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"
                ),
            ),
        ),
    ]

    report: Optional[WeatherReport] = await accuweather.get_weather_report(
        weather_context_without_location_key
    )

    assert report is None


@pytest.mark.parametrize(
    "weather_context",
    [
        WeatherContext(
            Location(
                country="US",
                regions=["CA"],
                dma=807,
            ),
            ["en-US"],
        ),
        WeatherContext(
            Location(
                regions=["CA"],
                city="San Francisco",
                dma=807,
                postal_code="94105",
            ),
            ["en-US"],
        ),
    ],
    ids=["country", "city"],
)
@pytest.mark.asyncio
async def test_get_weather_report_invalid_location(
    accuweather: AccuweatherBackend,
    weather_context: WeatherContext,
    statsd_mock: Any,
) -> None:
    """Test that the get_weather_report method raises an error if location information
    is missing.
    """
    expected_result = None
    with pytest.raises(MissingLocationKeyError):
        result = await accuweather.get_weather_report(weather_context)

        assert expected_result == result

        metrics_called = [
            (call_arg[0][0], call_arg[1]["sample_rate"])
            for call_arg in statsd_mock.increment.call_args_list
        ]
        assert metrics_called == [
            ("accuweather.request.location.not_provided", ACCUWEATHER_METRICS_SAMPLE_RATE)
        ]


@pytest.mark.asyncio
async def test_get_weather_report_with_city_in_skip_list(
    accuweather: AccuweatherBackend,
    statsd_mock: Any,
) -> None:
    """Test that the get_weather_report method raises an error if location information
    is missing.
    """
    expected_result = None
    increment_skip_cities_mapping("CA", "ON", "North Park")

    weather_context = WeatherContext(
        Location(
            regions=["ON"],
            city="North Park",
            country="CA",
            dma=807,
            postal_code="94105",
        ),
        ["en-US"],
    )

    assert get_skip_cities_mapping().get(("CA", "ON", "North Park")) == 1
    with pytest.raises(MissingLocationKeyError):
        result = await accuweather.get_weather_report(weather_context)

        assert expected_result == result

        assert get_skip_cities_mapping().get(("CA", "ON", "North Park")) == 2


@pytest.mark.asyncio
async def test_get_location_by_geolocation(
    accuweather: AccuweatherBackend,
    accuweather_location_response: bytes,
    response_header,
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that the get_location method returns an AccuweatherLocation."""
    expected_location: AccuweatherLocation = AccuweatherLocation(
        key="39376",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    weather_context_without_location_key.selected_region = "CA"
    weather_context_without_location_key.selected_city = "San Francisco"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_location_response,
        request=Request(
            method="GET",
            url=(
                "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                "apikey=test&q=San%20Francisco"
            ),
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location_by_geolocation(
        weather_context_without_location_key
    )

    assert location == expected_location


@pytest.mark.asyncio
async def test_get_location_no_location_returned(
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that the get_location method returns None if the response content is not as
    expected.
    """
    weather_context_without_location_key.selected_region = "CA"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=(
                "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                "apikey=test&q=San%20Francisco"
            ),
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location_by_geolocation(
        weather_context_without_location_key
    )

    assert location is None


@pytest.mark.parametrize(
    "weather_context",
    [
        WeatherContext(Location(country="US", city=None), languages=[]),
        WeatherContext(Location(country=None, city="N/A"), languages=[]),
    ],
    ids=["no-city", "no-country"],
)
@pytest.mark.asyncio
async def test_get_location_with_missing_country_city(
    accuweather: AccuweatherBackend, weather_context: WeatherContext
) -> None:
    """Test that the get_location method returns None without valid country and city."""
    location: Optional[AccuweatherLocation] = await accuweather.get_location_by_geolocation(
        weather_context
    )

    assert location is None


@pytest.mark.asyncio
async def test_get_location_by_geolocation_error(
    accuweather: AccuweatherBackend, weather_context_without_location_key: WeatherContext
) -> None:
    """Test that the get_location method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected location response from: /locations/v1/cities/US/CA/search.json, city: San Francisco"
    weather_context_without_location_key.selected_region = "CA"
    weather_context_without_location_key.selected_city = "San Francisco"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=403,
        content=(
            b"{"
            b'"Code":"Unauthorized",'
            b'"Message":"Api Authorization failed",'
            b'"Reference":"/locations/v1/cities/US/CA/search.json?apikey=&details=true"'
            b"}"
        ),
        request=Request(
            method="GET",
            url=(
                "https://www.accuweather.com/locations/v1/cities/US/CA/search.json?"
                "apikey=test&q=San%20Francisco"
            ),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location_by_geolocation(weather_context_without_location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_location_by_geolocation_raises_accuweather_error_on_generic_exception_error(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that the get_location_by_geolocation method raises an AccuweatherError when a generic
    exception happens.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.side_effect = ValueError
    weather_context_without_location_key.selected_region = "CA"
    weather_context_without_location_key.selected_city = "San Francisco"

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location_by_geolocation(weather_context_without_location_key)
    expected_error_value = (
        "Unexpected error occurred when requesting location by geolocation "
        "from Accuweather: ValueError"
    )
    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_current_conditions_url"],
    [
        (
            "accuweather",
            "https://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/"
            "39376?lang=en-us&partner=test_newtab",
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
    language: str,
) -> None:
    """Test that the get_current_conditions method returns CurrentConditionsWithTTL."""
    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
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
    location_key: str = "39376"
    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_current_conditions_response,
        request=Request(
            method="GET",
            url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
        ),
    )

    conditions: Optional[CurrentConditionsWithTTL] = await accuweather.get_current_conditions(
        location_key, language
    )

    assert conditions == expected_conditions


@pytest.mark.asyncio
async def test_get_current_conditions_no_current_conditions_returned(
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
    language: str,
) -> None:
    """Test that the get_current_conditions method returns None if the response content
    is not as expected.
    """
    location_key: str = "39376"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url=("http://www.accuweather.com/currentconditions/v1/39376.json?" "apikey=test"),
        ),
    )

    conditions: Optional[CurrentConditionsWithTTL] = await accuweather.get_current_conditions(
        location_key, language
    )

    assert conditions is None


@pytest.mark.asyncio
async def test_get_current_conditions_error(
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
    language: str,
) -> None:
    """Test that the get_current_conditions method raises an appropriate exception in
    the event of an AccuWeather API error.
    """
    expected_error_value: str = (
        "Unexpected current conditions response, Url: /currentconditions/v1/INVALID.json"
    )
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
            url=("http://www.accuweather.com/currentconditions/v1/INVALID.json?" "apikey=test"),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_current_conditions(location_key, language)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_forecast_url"],
    [
        (
            "accuweather",
            "https://www.accuweather.com/en/us/san-francisco-ca/94103/daily-weather-forecast/"
            "39376?lang=en-us&partner=test_newtab",
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
    language: str,
    accuweather_fixture: str,
    forecast_response_fixture: str,
    expected_forecast_url: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns a ForecastWithTTl."""
    # This request flow hits the store_request_into_cache method that returns the ttl. Mocking
    # that call to return the default weather report ttl
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
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

    location_key: str = "39376"
    content: bytes = request.getfixturevalue(forecast_response_fixture)
    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=content,
        request=Request(
            method="GET",
            url=("http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"),
        ),
    )

    forecast: Optional[ForecastWithTTL] = await accuweather.get_forecast(location_key, language)

    assert forecast == expected_forecast


@pytest.mark.asyncio
async def test_get_forecast_no_forecast_returned(
    accuweather: AccuweatherBackend,
    language: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns None if the response content is not as
    expected.
    """
    location_key: str = "39376"
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"{}",
        request=Request(
            method="GET",
            url=("http://www.accuweather.com/forecasts/v1/daily/1day/39376.json?" "apikey=test"),
        ),
    )

    forecast: Optional[ForecastWithTTL] = await accuweather.get_forecast(location_key, language)

    assert forecast is None


@pytest.mark.asyncio
async def test_get_forecast_error(accuweather: AccuweatherBackend, language: str) -> None:
    """Test that the get_forecast method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = (
        "Unexpected forecast response, Url: /forecasts/v1/daily/1day/INVALID.json"
    )
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
            url=("http://www.accuweather.com/forecasts/v1/daily/1day/INVALID.json?" "apikey=test"),
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_forecast(location_key, language)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ("query_params", "expected_cache_key"),
    [
        (
            {"q": "asdfg", "apikey": "filter_me_out"},
            f"AccuweatherBackend:v7:localhost:"
            f"{hashlib.blake2s('q'.encode('utf-8') + 'asdfg'.encode('utf-8')).hexdigest()}",
        ),
        (
            {},
            "AccuweatherBackend:v7:localhost",
        ),
        (
            {"q": "asdfg"},
            f"AccuweatherBackend:v7:localhost:"
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
    cache_key = accuweather.cache_key_for_accuweather_request(url, query_params=query_params)
    assert cache_key == expected_cache_key


@pytest.mark.parametrize(
    ("url", "expected_request_type"),
    [
        ("/forecasts/v1/daily/1day/39376.json", RequestType.FORECASTS),
        (
            "/currentconditions/v1/39376.json",
            RequestType.CURRENT_CONDITIONS,
        ),
    ],
    ids=["cache_miss", "deserialization_error"],
)
@freezegun.freeze_time("2023-04-09")
@pytest.mark.asyncio
async def test_request_upstream_cache_get_errors(
    accuweather: AccuweatherBackend,
    url: str,
    expected_request_type: RequestType,
    statsd_mock: Any,
):
    """Test for cache errors/misses. Ensures that the right metrics are
    called and that the API request is actually made.
    """
    expiry_date = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=2)
    expected_client_response = {"hello": "world", "cached_request_ttl": 0}

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=orjson.dumps(expected_client_response),
        request=Request(
            method="GET",
            url=f"https://www.accuweather.com/{url}?apikey=test",
        ),
    )

    results: Optional[dict[str, Any]] = await accuweather.request_upstream(
        url,
        {"apikey": "test"},
        expected_request_type,
        lambda a: cast(Optional[dict[str, Any]], a),
        TEST_CACHE_TTL_SEC,
    )

    assert expected_client_response == results

    timeit_metrics_called = [
        (call_arg[0][0], call_arg[1]["sample_rate"])
        for call_arg in statsd_mock.timeit.call_args_list
    ]

    assert [
        (f"accuweather.request.{expected_request_type}.get", ACCUWEATHER_METRICS_SAMPLE_RATE),
        (
            "accuweather.cache.store",
            ACCUWEATHER_METRICS_SAMPLE_RATE,
        ),
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
    url = "/forecasts/v1/daily/1day/39376.json"

    redis_mock.get.side_effect = CacheMissError
    redis_mock.set.side_effect = CacheAdapterError("Failed to set key with error: MockError")

    expiry_date = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=2)
    expected_client_response = {"hello": "world"}

    accuweather: AccuweatherBackend = AccuweatherBackend(
        cache=redis_mock, **accuweather_parameters
    )

    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=orjson.dumps(expected_client_response),
        request=Request(
            method="GET",
            url=f"https://www.accuweather.com/{url}?apikey=test",
        ),
    )

    with pytest.raises(AccuweatherError):
        await accuweather.request_upstream(
            url,
            params={"apikey": "test"},
            request_type=RequestType.FORECASTS,
            process_api_response=lambda a: cast(Optional[dict[str, Any]], a),
            cache_ttl_sec=TEST_CACHE_TTL_SEC,
        )

    timeit_metrics_called = [
        (call_arg[0][0], call_arg[1]["sample_rate"])
        for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert [
        ("accuweather.request.forecasts.get", ACCUWEATHER_METRICS_SAMPLE_RATE),
        ("accuweather.cache.store", ACCUWEATHER_METRICS_SAMPLE_RATE),
    ] == timeit_metrics_called

    increment_called = [call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list]
    assert [
        f"accuweather.upstream.request.{RequestType.FORECASTS}.get",
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


def test_update_weather_url_with_suggest_partner_code(
    accuweather_cached_current_conditions, accuweather_cached_forecast_fahrenheit
):
    """Test update_weather_url_with_suggest_partner_code correctly updates the partner param"""
    current_conditions_data = orjson.loads(accuweather_cached_current_conditions.decode("utf-8"))
    forecast_data = orjson.loads(accuweather_cached_forecast_fahrenheit.decode("utf-8"))
    current_conditions = CurrentConditions(**current_conditions_data)
    forecast = Forecast(**forecast_data)

    modified_current_conditions, modified_forecast = update_weather_url_with_suggest_partner_code(
        current_conditions, forecast
    )
    assert modified_current_conditions.url == HttpUrl(
        "https://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/39376?lang=en-us&partner=test_urlbar"
    )
    assert modified_forecast.url == HttpUrl(
        "https://www.accuweather.com/en/us/san-francisco-ca/94103/daily-weather-forecast/39376?lang=en-us&partner=test_urlbar"
    )


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
        (call_arg[0][0], call_arg[1]["sample_rate"])
        for call_arg in statsd_mock.increment.call_args_list
    ]
    assert [
        (f"accuweather.cache.{val}", ACCUWEATHER_METRICS_SAMPLE_RATE) for val in expected_metrics
    ] == metrics_called


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
            "accuweather_cached_data_partial_miss_ttl",
            "accuweather_parsed_data_partial_miss_ttl",
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
        "partial-miss-ttl",
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
            b"{}",
            b"{}",
            None,
        ]
    )

    assert location == AccuweatherLocation.model_validate_json(accuweather_cached_location_key)
    assert current_conditions is None
    assert forecast is None

    metrics_called = [call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list]
    assert metrics_called == ["accuweather.cache.data.error"]

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.weather.backends.accuweather.backend"
    )

    assert len(caplog.records) == 1
    assert records[0].message.startswith("Failed to load weather report data from Redis:")


@pytest.mark.asyncio
async def test_get_location_completion(
    accuweather: AccuweatherBackend,
    expected_location_completion: list[LocationCompletion],
    weather_context_without_location_key: WeatherContext,
    accuweather_location_completion_response: bytes,
) -> None:
    """Test that the get_location_completion method returns a list of LocationCompletion."""
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    search_term = "new"
    geolocation = weather_context_without_location_key.geolocation

    client_mock.get.side_effect = [
        Response(
            status_code=200,
            content=accuweather_location_completion_response,
            request=Request(
                method="GET",
                url=(
                    f"https://www.accuweather.com/locations/v1/"
                    f"{geolocation.country}/autocomplete.json?apikey=test&q"
                    f"={search_term}"
                ),
            ),
        )
    ]

    location_completions: Optional[
        list[LocationCompletion]
    ] = await accuweather.get_location_completion(
        weather_context_without_location_key, search_term
    )

    assert location_completions == expected_location_completion


@pytest.mark.asyncio
async def test_get_location_completion_with_invalid_accuweather_response(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    statsd_mock: Any,
) -> None:
    """Test that the get_location_completion method returns None
    when the response json received by accuweather is of invalid shape
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    geolocation = weather_context_without_location_key.geolocation

    search_term = "new"
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            content=b"{}",  # response will be an empty object
            request=Request(
                method="GET",
                url=(
                    f"https://www.accuweather.com/locations/v1/"
                    f"{geolocation.country}/autocomplete.json?apikey=test&q"
                    f"={search_term}"
                ),
            ),
        )
    ]

    location_completions: Optional[
        list[LocationCompletion]
    ] = await accuweather.get_location_completion(
        weather_context_without_location_key, search_term
    )

    metrics_called = [call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list]
    assert [
        f"accuweather.upstream.request.{RequestType.AUTOCOMPLETE}.get",
        f"accuweather.request.{RequestType.AUTOCOMPLETE}.processor.error",
    ] == metrics_called

    # assert that None is returned from the function
    assert location_completions is None


@pytest.mark.asyncio
async def test_get_location_completion_raises_accuweather_error_on_catching_generic_exception(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that the get_location_completion catches a generic Exception and raises it as an
    AccuweatherError
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    search_term = "new"

    client_mock.get.side_effect = SSLError

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location_completion(
            weather_context_without_location_key, search_term
        )

    expected_error_message = (
        "Unexpected error occurred when requesting location completion "
        "from Accuweather: SSLError"
    )

    assert expected_error_message == str(accuweather_error.value)


@pytest.mark.asyncio
async def test_get_location_completion_raises_accuweather_error_on_catching_http_error(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that the get_location_completion catches an HTTPError and raises it as an
    AccuweatherError
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    search_term = "new"

    geolocation = weather_context_without_location_key.geolocation
    languages = weather_context_without_location_key.languages

    # we are returning a 404 http response
    client_mock.get.side_effect = [
        Response(
            status_code=404,
            content=b'{"detail": "Not Found"}',  # response will be an empty object
            request=Request(
                method="GET",
                url=(
                    f"https://www.accuweather.com/locations/v1/"
                    f"{geolocation.country}/autocomplete.json?apikey=test&q"
                    f"={search_term}"
                ),
            ),
        )
    ]

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location_completion(
            weather_context_without_location_key, search_term
        )

    url_path = f"/locations/v1/cities/{geolocation.country}/autocomplete.json"
    expected_error_message = (
        f"Failed to get location completion from Accuweather, http error occurred. "
        f"Url path: {url_path}, query: {search_term}, language: {languages[0]}"
    )

    assert expected_error_message == str(accuweather_error.value)


@pytest.mark.asyncio
async def test_get_location_completion_with_empty_search_term(
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
    accuweather_location_completion_response: bytes,
) -> None:
    """Test that the get_location_completion method returns None when the search_term parameter
    is an empty string.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    search_term = ""
    geolocation = weather_context_without_location_key.geolocation
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            content=accuweather_location_completion_response,
            request=Request(
                method="GET",
                url=(
                    f"https://www.accuweather.com/locations/v1/"
                    f"{geolocation.country}/autocomplete.json?apikey=test&q"
                    f"={search_term}"
                ),
            ),
        )
    ]

    location_completions: Optional[
        list[LocationCompletion]
    ] = await accuweather.get_location_completion(
        weather_context_without_location_key, search_term
    )

    assert location_completions is None


@pytest.mark.asyncio
async def test_get_location_completion_with_no_geolocation_country_code(
    accuweather: AccuweatherBackend,
    expected_location_completion: list[LocationCompletion],
    weather_context_without_location_key: WeatherContext,
    accuweather_location_completion_response: bytes,
) -> None:
    """Test that the get_location_completion method returns a list of LocationCompletion
    when no geolocation country code is provided.
    """
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)

    search_term = "new"
    geolocation = weather_context_without_location_key.geolocation
    geolocation.country = None
    client_mock.get.side_effect = [
        Response(
            status_code=200,
            content=accuweather_location_completion_response,
            request=Request(
                method="GET",
                url=(
                    f"https://www.accuweather.com/locations/v1/autocomplete.json?"
                    f"apikey=test&q{search_term}"
                ),
            ),
        )
    ]

    location_completions: Optional[
        list[LocationCompletion]
    ] = await accuweather.get_location_completion(
        weather_context_without_location_key, search_term
    )

    assert location_completions == expected_location_completion


@pytest.mark.asyncio
async def test_fetch_from_cache_without_country_city(
    accuweather: AccuweatherBackend, language: str
) -> None:
    """Test that `_fetch_from_cache` returns None if country or city is missing."""
    weather_context = WeatherContext(Location(country="US"), languages=["en-US"])
    cached_data = await accuweather._fetch_from_cache(weather_context)

    assert cached_data is None

    weather_context.geolocation.country = None
    cached_data = await accuweather._fetch_from_cache(weather_context)

    assert cached_data is None


@pytest.mark.parametrize(
    ("languages", "expected_selected_language"),
    [
        (["en-US"], "en-US"),
        (["invalid", "de", "en-US"], "de"),
        (["invalid", "bad-language"], "en-US"),
    ],
)
def test_get_languages(languages, expected_selected_language) -> None:
    """Test return language returns the first valid language."""
    assert get_language(languages) == expected_selected_language


@pytest.mark.parametrize(
    ("languages", "expected_city_name"),
    [
        (["en-US"], "San Francisco"),
        (["fr"], "Sân Frâncisco"),
        (["it"], None),
        (["es-MX"], "Sán Fráncisco"),
    ],
)
@pytest.mark.asyncio
async def test_get_localized_city_name(
    weather_context_without_location_key: WeatherContext,
    languages: list[str],
    expected_city_name: str,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test return city name returns correct localized city name."""
    location = AccuweatherLocation(
        key="123",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    modified_weather_context = replace(weather_context_without_location_key, languages=languages)
    city_name = accuweather.get_localized_city_name(location, modified_weather_context)
    assert city_name == expected_city_name


@pytest.mark.parametrize(
    ("country_request_origin", "expected_region"),
    [
        ("United States", "CA"),
        ("France", "United States"),
        (None, "United States"),
    ],
)
@pytest.mark.asyncio
async def test_get_region_for_weather_report_north_america(
    weather_context_without_location_key: WeatherContext,
    country_request_origin: str,
    expected_region: str,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test return city name returns correct localized city name."""
    location = AccuweatherLocation(
        key="123",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    geolocation = weather_context_without_location_key.geolocation
    modified_geolocation = geolocation.model_copy(update={"country_name": country_request_origin})
    modified_weather_context = replace(
        weather_context_without_location_key, geolocation=modified_geolocation
    )
    region = accuweather.get_region_for_weather_report(location, modified_weather_context)
    assert region == expected_region


@pytest.mark.parametrize(
    ("country_request_origin", "request_country", "expected_region"),
    [
        ("United States", "GB", "United Kingdom"),
        ("United Kingdom", "GB", "United Kingdom"),
        (None, "GB", "United Kingdom"),
    ],
)
@pytest.mark.asyncio
async def test_get_region_for_weather_report_outside_north_america(
    weather_context_without_location_key: WeatherContext,
    country_request_origin: str,
    request_country: str,
    expected_region: str,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test return city name returns correct localized city name."""
    location = AccuweatherLocation(
        key="123",
        localized_name="London",
        administrative_area_id="LND",
        country_name="United Kingdom",
    )
    geolocation = weather_context_without_location_key.geolocation
    modified_geolocation = geolocation.model_copy(
        update={"country_name": country_request_origin, "country": request_country}
    )
    modified_weather_context = replace(
        weather_context_without_location_key, geolocation=modified_geolocation
    )
    region = accuweather.get_region_for_weather_report(location, modified_weather_context)
    assert region == expected_region


@pytest.mark.asyncio
async def test_get_hourly_forecasts(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_with_location_key: WeatherContext,
    accuweather_hourly_forecast_response: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that get_hourly_forecasts returns HourlyForecastsWithTTL with valid API response."""
    # Mock pathfinder.explore to return AccuweatherLocation
    accuweather_location = AccuweatherLocation(
        key="39376",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.pathfinder.explore"
    ).return_value = (accuweather_location, None)

    # Mock cache run_script to return cache miss (None, -2)
    mocker.patch.object(accuweather.cache, "run_script", return_value=[None, -2])

    # Mock store_request_into_cache to return TEST_CACHE_TTL_SEC
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.AccuweatherBackend"
        ".store_request_into_cache"
    ).return_value = TEST_CACHE_TTL_SEC

    # Mock HTTP client to return hourly forecast response
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_hourly_forecast_response,
        request=Request(
            method="GET",
            url="http://www.accuweather.com/forecasts/v1/hourly/12hour/39376.json?apikey=test",
        ),
    )

    # Call get_hourly_forecasts
    result: Optional[HourlyForecastsWithTTL] = await accuweather.get_hourly_forecasts(
        weather_context_with_location_key
    )

    # Assertions
    assert result is not None
    assert isinstance(result, HourlyForecastsWithTTL)
    assert len(result.hourly_forecasts) == 5  # DEFAULT_FORECAST_HOURS
    assert result.ttl == TEST_CACHE_TTL_SEC

    # Verify first forecast structure
    first_forecast = result.hourly_forecasts[0]
    assert first_forecast.date_time == "2026-02-18T14:00:00-05:00"
    assert first_forecast.epoch_date_time == 1708281600
    assert first_forecast.temperature.f == 60
    assert first_forecast.temperature.c == 16
    assert first_forecast.icon_id == 6
    assert "hourly-weather-forecast/39376?day=1&hbhhour=14" in str(first_forecast.url)


@pytest.mark.asyncio
async def test_get_hourly_forecasts_missing_location_key(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_without_location_key: WeatherContext,
) -> None:
    """Test that get_hourly_forecasts raises MissingLocationKeyError when location key is None."""
    # Mock pathfinder.explore to return (None, None)
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.pathfinder.explore"
    ).return_value = (None, None)

    # Assert that MissingLocationKeyError is raised
    with pytest.raises(MissingLocationKeyError):
        await accuweather.get_hourly_forecasts(weather_context_without_location_key)

    # Verify HTTP client was never called
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_hourly_forecasts_cache_hit(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_with_location_key: WeatherContext,
    accuweather_hourly_forecast_response: bytes,
) -> None:
    """Test that get_hourly_forecasts returns cached data when available."""
    # Mock pathfinder.explore to return AccuweatherLocation
    accuweather_location = AccuweatherLocation(
        key="39376",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.pathfinder.explore"
    ).return_value = (accuweather_location, None)

    # Process the API response fixture to get cached format
    api_response = orjson.loads(accuweather_hourly_forecast_response)
    processed_data = process_hourly_forecast_response(api_response)
    cached_data = orjson.dumps(processed_data)
    cached_ttl = TEST_HOURLY_FORECASTS_CACHE_TTL_SEC

    # Mock cache run_script to return cache hit
    mocker.patch.object(accuweather.cache, "run_script", return_value=[cached_data, cached_ttl])

    # Call get_hourly_forecasts
    result: Optional[HourlyForecastsWithTTL] = await accuweather.get_hourly_forecasts(
        weather_context_with_location_key
    )

    # Assertions
    assert result is not None
    assert isinstance(result, HourlyForecastsWithTTL)
    assert len(result.hourly_forecasts) == 5  # DEFAULT_FORECAST_HOURS
    assert result.ttl == cached_ttl

    # Verify first forecast structure from cache
    first_forecast = result.hourly_forecasts[0]
    assert first_forecast.date_time == "2026-02-18T14:00:00-05:00"
    assert first_forecast.temperature.f == 60
    assert first_forecast.temperature.c == 16

    # Verify HTTP client was never called (cache hit)
    client_mock: AsyncMock = cast(AsyncMock, accuweather.http_client)
    client_mock.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_hourly_forecasts_api_returns_none(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_with_location_key: WeatherContext,
) -> None:
    """Test that get_hourly_forecasts returns None when API returns invalid response."""
    # Mock pathfinder.explore to return AccuweatherLocation
    accuweather_location = AccuweatherLocation(
        key="39376",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.pathfinder.explore"
    ).return_value = (accuweather_location, None)

    # Mock cache run_script to return cache miss
    mocker.patch.object(accuweather.cache, "run_script", return_value=[None, -2])

    # Mock request_upstream to return None (simulating invalid API response)
    mocker.patch.object(accuweather, "request_upstream", return_value=None)

    # Call get_hourly_forecasts
    result: Optional[HourlyForecastsWithTTL] = await accuweather.get_hourly_forecasts(
        weather_context_with_location_key
    )

    # Assert result is None
    assert result is None


@pytest.mark.asyncio
async def test_get_hourly_forecasts_validation_error(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    weather_context_with_location_key: WeatherContext,
) -> None:
    """Test that get_hourly_forecasts returns None when response validation fails."""
    # Mock pathfinder.explore to return AccuweatherLocation
    accuweather_location = AccuweatherLocation(
        key="39376",
        localized_name="San Francisco",
        administrative_area_id="CA",
        country_name="United States",
    )
    mocker.patch(
        "merino.providers.suggest.weather.backends.accuweather.pathfinder.explore"
    ).return_value = (accuweather_location, None)

    # Mock cache run_script to return cache miss
    mocker.patch.object(accuweather.cache, "run_script", return_value=[None, -2])

    # Mock request_upstream to return malformed data (hourly_forecasts with invalid structure)
    mocker.patch.object(
        accuweather,
        "request_upstream",
        return_value={
            "hourly_forecasts": [{"invalid": "data"}],  # Missing required fields
            "cached_request_ttl": TEST_HOURLY_FORECASTS_CACHE_TTL_SEC,
        },
    )

    # Call get_hourly_forecasts
    result: Optional[HourlyForecastsWithTTL] = await accuweather.get_hourly_forecasts(
        weather_context_with_location_key
    )

    # Assert result is None due to KeyError
    assert result is None
