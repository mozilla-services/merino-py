# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AccuWeather backend module."""
import datetime
import hashlib
import json
from typing import Any, Optional
from unittest.mock import AsyncMock

import freezegun
import pytest
from httpx import AsyncClient, HTTPError, Request, Response
from pydantic.datetime_parse import datetime as datetime_type
from pytest import FixtureRequest
from pytest_mock import MockerFixture
from redis.asyncio import Redis

from merino.cache.redis import RedisAdapter
from merino.exceptions import CacheAdapterError, CacheEntryError, CacheMissError
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.accuweather import (
    AccuweatherBackend,
    AccuweatherError,
    AccuweatherLocation,
)
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)

ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"


@pytest.fixture(name="redis_mock_cache_miss")
def fixture_redis_mock_cache_miss(mocker: MockerFixture) -> Any:
    """Create a Redis client mock object for testing."""

    async def mock_get(key) -> Any:
        return None

    async def mock_set(key, value, **kwargs) -> Any:
        return None

    mock = mocker.AsyncMock(spec=Redis)
    mock.get.side_effect = mock_get
    mock.set.side_effect = mock_set
    return mock


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters(statsd_mock: Any) -> dict[str, Any]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "cached_report_ttl_sec": 1800,
        "metrics_client": statsd_mock,
        "url_base": "test://test",
        "url_param_api_key": "apikey",
        "url_postalcodes_path": "/locations/v1/postalcodes/{country_code}/search.json",
        "url_postalcodes_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
    }


@pytest.fixture(name="response_header")
def fixture_response_header() -> dict[str, str]:
    """Create a response header with a reasonable expiry."""
    expiry_time: datetime_type = datetime.datetime.now(
        tz=datetime.timezone.utc
    ) + datetime.timedelta(days=2)
    return {"Expires": expiry_time.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)}


@pytest.fixture(name="accuweather")
def fixture_accuweather(
    redis_mock_cache_miss: AsyncMock,
    accuweather_parameters: dict[str, Any],
    statsd_mock: Any,
) -> AccuweatherBackend:
    """Create an Accuweather object for test. This object always have cache miss."""
    return AccuweatherBackend(
        cache=RedisAdapter(redis_mock_cache_miss),
        **accuweather_parameters,
    )


@pytest.fixture(name="accuweather_with_partner_code")
def fixture_accuweather_with_partner_code(
    redis_mock_cache_miss: AsyncMock, accuweather_parameters: dict[str, Any]
) -> AccuweatherBackend:
    """Create an Accuweather object with a partner code for test."""
    return AccuweatherBackend(
        url_param_partner_code="partner",
        partner_code="acme",
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
        "url_base",
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
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns a WeatherReport."""
    expected_report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
                "daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
    )
    return_values: list[Response] = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
            ),
        ),
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=return_values)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report == expected_report


@pytest.mark.asyncio
async def test_get_weather_report_failed_location_query(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    geolocation: Location,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    postal code search query yields no result.
    """
    return_value: Response = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
        ),
    )
    mocker.patch.object(AsyncClient, "get", return_value=return_value)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None


@pytest.mark.asyncio
async def test_get_weather_report_failed_current_conditions_query(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    current conditions query yields no result.
    """
    side_effects: list[Response] = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=b"[]",
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_forecast_response_fahrenheit,
            request=Request(
                method="GET",
                url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
            ),
        ),
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=side_effects)

    report: Optional[WeatherReport] = await accuweather.get_weather_report(geolocation)

    assert report is None


@pytest.mark.asyncio
async def test_get_weather_report_handles_exception_group_properly(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method raises an error if current condition call throws
    an error
    """
    side_effects: list[Response | HTTPError] = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        HTTPError("Invalid Request - Current Conditions"),
        HTTPError("Invalid Request - Forecast"),
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=side_effects)
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
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    response_header: dict[str, str],
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    forecast query yields no result.
    """
    side_effects: list[Response] = [
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
            headers=response_header,
            content=b"{}",
            request=Request(
                method="GET",
                url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
            ),
        ),
    ]
    mocker.patch.object(AsyncClient, "get", side_effect=side_effects)

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
    mocker: MockerFixture,
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
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_location_response,
        request=Request(
            method="GET",
            url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location(
        mock_client, country, postal_code
    )

    assert location == expected_location


@pytest.mark.asyncio
async def test_get_location_from_cache(
    mocker: MockerFixture,
    accuweather_parameters: dict[str, Any],
    accuweather_location_response: bytes,
    response_header,
) -> None:
    """Test that we can get the location from cache."""
    redis_mock = mocker.AsyncMock(spec=Redis)

    async def mock_get(key) -> Any:
        return accuweather_location_response

    redis_mock.get.side_effect = mock_get

    expected_location: AccuweatherLocation = AccuweatherLocation(
        key="39376_PC", localized_name="San Francisco"
    )
    country: str = "US"
    postal_code: str = "94105"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)

    accuweather = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    location: Optional[AccuweatherLocation] = await accuweather.get_location(
        mock_client, country, postal_code
    )

    assert location == expected_location
    expected_query_string = "q".encode("utf-8") + postal_code.encode("utf-8")
    redis_mock.get.assert_called_once_with(
        f"AccuweatherBackend:v1:/locations/v1/postalcodes/{country}/search.json:"
        f"{hashlib.blake2s(expected_query_string).hexdigest()}"
    )
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_location_no_location_returned(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test that the get_location method returns None if the response content is not as
    expected.
    """
    country: str = "US"
    postal_code: str = "94105"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
        ),
    )

    location: Optional[AccuweatherLocation] = await accuweather.get_location(
        mock_client, country, postal_code
    )

    assert location is None


@pytest.mark.asyncio
async def test_get_location_error(
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_location method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected location response"
    country: str = "US"
    postal_code: str = "94105"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
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
            url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_location(mock_client, country, postal_code)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_current_conditions_url"],
    [
        (
            "accuweather",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/"
            "39376_pc?lang=en-us",
        ),
        (
            "accuweather_with_partner_code",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/"
            "39376_pc?lang=en-us&partner=acme",
        ),
    ],
    ids=["without_partner_code", "with_partner_code"],
)
@pytest.mark.asyncio
async def test_get_current_conditions(
    request: FixtureRequest,
    mocker: MockerFixture,
    accuweather_fixture: str,
    accuweather_current_conditions_response: bytes,
    expected_current_conditions_url: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_current_conditions method returns CurrentConditions."""
    expected_conditions: CurrentConditions = CurrentConditions(
        url=expected_current_conditions_url,
        summary="Mostly cloudy",
        icon_id=6,
        temperature=Temperature(c=15.5, f=60),
    )
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=accuweather_current_conditions_response,
        request=Request(
            method="GET",
            url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
        ),
    )

    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    conditions: Optional[CurrentConditions] = await accuweather.get_current_conditions(
        mock_client, location_key
    )

    assert conditions == expected_conditions


@pytest.mark.asyncio
async def test_get_current_conditions_from_cache(
    mocker: MockerFixture,
    accuweather_parameters: dict[str, Any],
    accuweather_current_conditions_response: bytes,
):
    """Get the current condition from cache. Do not make an API call."""
    redis_mock = mocker.AsyncMock(spec=Redis)

    async def mock_get(key):
        return accuweather_current_conditions_response

    redis_mock.get.side_effect = mock_get
    current_conditions_url = (
        "http://www.accuweather.com/en/us/san-francisco-ca/"
        "94103/current-weather/39376_pc?lang=en-us"
    )

    expected_conditions: CurrentConditions = CurrentConditions(
        url=current_conditions_url,
        summary="Mostly cloudy",
        icon_id=6,
        temperature=Temperature(c=15.5, f=60),
    )
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)

    accuweather = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    conditions: Optional[CurrentConditions] = await accuweather.get_current_conditions(
        mock_client, location_key
    )
    assert conditions == expected_conditions
    redis_mock.get.assert_called_once_with(
        "AccuweatherBackend:v1:/currentconditions/v1/39376_PC.json"
    )
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_conditions_no_current_conditions_returned(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test that the get_current_conditions method returns None if the response content
    is not as expected.
    """
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"[]",
        request=Request(
            method="GET",
            url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
        ),
    )

    conditions: Optional[CurrentConditions] = await accuweather.get_current_conditions(
        mock_client, location_key
    )

    assert conditions is None


@pytest.mark.asyncio
async def test_get_current_conditions_error(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test that the get_current_conditions method raises an appropriate exception in
    the event of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected current conditions response"
    location_key: str = "INVALID"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
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
            url="test://test/currentconditions/v1/INVALID.json?apikey=test",
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_current_conditions(mock_client, location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ["accuweather_fixture", "expected_forecast_url"],
    [
        (
            "accuweather",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/daily-weather-forecast/"
            "39376_pc?lang=en-us",
        ),
        (
            "accuweather_with_partner_code",
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/daily-weather-forecast/"
            "39376_pc?lang=en-us&partner=acme",
        ),
    ],
    ids=["without_partner_code", "with_partner_code"],
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
    request: FixtureRequest,
    mocker: MockerFixture,
    accuweather_fixture: str,
    forecast_response_fixture: str,
    expected_forecast_url: str,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns a Forecast."""
    expected_forecast: Forecast = Forecast(
        url=expected_forecast_url,
        summary="Pleasant Saturday",
        high=Temperature(f=70),
        low=Temperature(f=57),
    )
    location_key: str = "39376_PC"
    content: bytes = request.getfixturevalue(forecast_response_fixture)
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=content,
        request=Request(
            method="GET",
            url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
        ),
    )

    accuweather: AccuweatherBackend = request.getfixturevalue(accuweather_fixture)
    forecast: Optional[Forecast] = await accuweather.get_forecast(
        mock_client, location_key
    )

    assert forecast == expected_forecast


@pytest.mark.asyncio
async def test_get_forecast_from_cache(
    mocker: MockerFixture,
    accuweather_parameters: dict[str, Any],
    accuweather_forecast_response_fahrenheit: bytes,
):
    """Get the forecast from cache. Do not make an API call."""
    redis_mock = mocker.AsyncMock(spec=Redis)

    async def mock_get(key):
        return accuweather_forecast_response_fahrenheit

    redis_mock.get.side_effect = mock_get

    expected_forecast_url = (
        "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
        "daily-weather-forecast/39376_pc?lang=en-us"
    )

    expected_forecast: Forecast = Forecast(
        url=expected_forecast_url,
        summary="Pleasant Saturday",
        high=Temperature(f=70),
        low=Temperature(f=57),
    )

    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)

    accuweather = AccuweatherBackend(
        cache=RedisAdapter(redis_mock), **accuweather_parameters
    )
    forecast: Optional[Forecast] = await accuweather.get_forecast(
        mock_client, location_key
    )
    assert forecast == expected_forecast
    redis_mock.get.assert_called_once_with(
        "AccuweatherBackend:v1:/forecasts/v1/daily/1day/39376_PC.json"
    )
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_forecast_no_forecast_returned(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    response_header: dict[str, str],
) -> None:
    """Test that the get_forecast method returns None if the response content is not as
    expected.
    """
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers=response_header,
        content=b"{}",
        request=Request(
            method="GET",
            url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
        ),
    )

    forecast: Optional[Forecast] = await accuweather.get_forecast(
        mock_client, location_key
    )

    assert forecast is None


@pytest.mark.asyncio
async def test_get_forecast_error(
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_forecast method raises an appropriate exception in the event
    of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected forecast response"
    location_key: str = "INVALID"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
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
            url="test://test/forecasts/v1/daily/1day/INVALID.json?apikey=test",
        ),
    )

    with pytest.raises(AccuweatherError) as accuweather_error:
        await accuweather.get_forecast(mock_client, location_key)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.parametrize(
    ("query_params", "expected_cache_key"),
    [
        (
            {"q": "asdfg", "apikey": "filter_me_out"},
            f"AccuweatherBackend:v1:localhost:"
            f"{hashlib.blake2s('q'.encode('utf-8') + 'asdfg'.encode('utf-8')).hexdigest()}",
        ),
        (
            {},
            "AccuweatherBackend:v1:localhost",
        ),
        (
            {"q": "asdfg"},
            f"AccuweatherBackend:v1:localhost:"
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


@pytest.mark.asyncio
async def test_get_request_cache_hit(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any], statsd_mock: Any
):
    """Test that request can get value from cache"""
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)
    url = "/forecasts/v1/daily/1day/39376_PC.json"

    async def mock_get(key):
        return json.dumps({"key": key}).encode("utf-8")

    redis_mock.get.side_effect = mock_get

    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)

    accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)

    results: dict[str, Any] = await accuweather.get_request(mock_client, url)
    assert results == {
        "key": "AccuweatherBackend:v1:/forecasts/v1/daily/1day/39376_PC.json"
    }

    statsd_mock.timeit.assert_called_once_with("accuweather.cache.fetch")
    statsd_mock.increment.assert_called_once_with("accuweather.cache.hit.forecasts")
    mock_client.get.assert_not_called()


@pytest.mark.parametrize(
    ("mock_cache_entry", "expected_cache_error_type", "url", "expected_url_type"),
    [
        (b"", "miss", "/forecasts/v1/daily/1day/39376_PC.json", "forecasts"),
        (
            b"can't serialize this",
            "error",
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
    accuweather_parameters: dict[str, Any],
    mock_cache_entry: bytes,
    expected_cache_error_type: str,
    response_header: dict[str, str],
    url: str,
    expected_url_type: str,
    statsd_mock: Any,
):
    """Test for cache errors/misses. Ensures that the right metrics are
    called and that the API request is actually made.
    """
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)

    cache = {}

    async def mock_get(key):
        return mock_cache_entry

    async def mock_store(key, value, ttl=None):
        assert ttl == datetime.timedelta(days=2)
        cache[key] = value

    redis_mock.get.side_effect = mock_get
    redis_mock.set.side_effect = mock_store

    expiry_date = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
        days=2
    )
    expected_client_response = {"hello": "world"}
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=json.dumps(expected_client_response).encode("utf-8"),
        request=Request(
            method="GET",
            url=f"test://test/{url}?apikey=test",
        ),
    )

    accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)
    results: dict[str, Any] = await accuweather.get_request(
        mock_client, url, params={"apikey": "test"}
    )
    assert expected_client_response == results

    timeit_metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert [
        "accuweather.cache.fetch",
        f"accuweather.request.{expected_url_type}.get",
        "accuweather.cache.store",
    ] == timeit_metrics_called

    statsd_mock.increment.assert_called_once_with(
        f"accuweather.cache.fetch.{expected_cache_error_type}.{expected_url_type}"
    )

    cache_key = f"AccuweatherBackend:v1:{url}"
    assert cache[cache_key] == json.dumps(expected_client_response).encode("utf-8")


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
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        headers={"Expires": expiry_date.strftime(ACCUWEATHER_CACHE_EXPIRY_DATE_FORMAT)},
        content=json.dumps(expected_client_response).encode("utf-8"),
        request=Request(
            method="GET",
            url=f"test://test/{url}?apikey=test",
        ),
    )

    with pytest.raises(AccuweatherError):
        accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)
        await accuweather.get_request(mock_client, url, params={"apikey": "test"})

    timeit_metrics_called = [
        call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list
    ]
    assert [
        "accuweather.cache.fetch",
        "accuweather.request.forecasts.get",
        "accuweather.cache.store",
    ] == timeit_metrics_called

    increment_called = [
        call_arg[0][0] for call_arg in statsd_mock.increment.call_args_list
    ]
    assert [
        "accuweather.cache.fetch.miss.forecasts",
        "accuweather.cache.store.set_error",
    ] == increment_called


@pytest.mark.parametrize(
    ("mock_cache_entry", "error"),
    [(b"", CacheMissError), (b"can't serialize this", CacheEntryError)],
    ids=["cache_miss", "deserialization_error"],
)
@pytest.mark.asyncio
async def test_fetch_request_from_cache_error(
    mocker: MockerFixture,
    accuweather_parameters: dict[str, Any],
    mock_cache_entry: bytes,
    error: Any,
):
    """Test that an error is raised for cache miss."""
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)

    async def mock_get(key):
        return mock_cache_entry

    redis_mock.get.side_effect = mock_get

    accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)

    with pytest.raises(error):
        await accuweather.fetch_request_from_cache("random_key")


@pytest.mark.asyncio
async def test_store_request_in_cache_error_invalid_expiry(
    mocker: MockerFixture, accuweather_parameters: dict[str, Any]
):
    """Test that an error is raised for cache miss."""
    redis_mock = mocker.AsyncMock(spec=RedisAdapter)

    accuweather = AccuweatherBackend(cache=redis_mock, **accuweather_parameters)

    with pytest.raises(ValueError):
        await accuweather.store_request_into_cache(
            "key", {"hello": "cache"}, "invalid_date_format"
        )
