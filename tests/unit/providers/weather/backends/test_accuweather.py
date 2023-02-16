# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AccuWeather backend module."""

import json
from typing import Any, Optional

import pytest
from httpx import AsyncClient, HTTPError, Request, Response
from pytest import FixtureRequest
from pytest_mock import MockerFixture

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


@pytest.fixture(name="accuweather_parameters")
def fixture_accuweather_parameters() -> dict[str, str]:
    """Create an Accuweather object for test."""
    return {
        "api_key": "test",
        "url_base": "test://test",
        "url_param_api_key": "apikey",
        "url_postalcodes_path": "/locations/v1/postalcodes/{country_code}/search.json",
        "url_postalcodes_param_query": "q",
        "url_current_conditions_path": "/currentconditions/v1/{location_key}.json",
        "url_forecasts_path": "/forecasts/v1/daily/1day/{location_key}.json",
    }


@pytest.fixture(name="accuweather")
def fixture_accuweather(accuweather_parameters: dict[str, str]) -> AccuweatherBackend:
    """Create an Accuweather object for test."""
    return AccuweatherBackend(**accuweather_parameters)


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


def test_init_api_key_value_error(accuweather_parameters: dict[str, str]) -> None:
    """Test that a ValueError is raised if initializing with an empty API key."""
    expected_error_value: str = "AccuWeather API key not specified"
    accuweather_parameters["api_key"] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(**accuweather_parameters)

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
    accuweather_parameters: dict[str, str], url_value: str
) -> None:
    """Test that a ValueError is raised if initializing with empty URL values."""
    expected_error_value: str = (
        "One or more AccuWeather API URL parameters are undefined"
    )
    accuweather_parameters[url_value] = ""

    with pytest.raises(ValueError) as accuweather_error:
        AccuweatherBackend(**accuweather_parameters)

    assert str(accuweather_error.value) == expected_error_value


@pytest.mark.asyncio
async def test_get_weather_report(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    geolocation: Location,
    accuweather_location_response: bytes,
    accuweather_current_conditions_response: bytes,
    accuweather_forecast_response_fahrenheit: bytes,
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
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
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
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    postal code search query yields no result.
    """
    return_value: Response = Response(
        status_code=200,
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
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    current conditions query yields no result.
    """
    side_effects: list[Response] = [
        Response(
            status_code=200,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            content=b"[]",
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
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
) -> None:
    """Test that the get_weather_report method raises an error if current condition call throws
    an error
    """
    side_effects: list[Response | HTTPError] = [
        Response(
            status_code=200,
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
) -> None:
    """Test that the get_weather_report method returns None if the AccuWeather
    forecast query yields no result.
    """
    side_effects: list[Response] = [
        Response(
            status_code=200,
            content=accuweather_location_response,
            request=Request(
                method="GET",
                url="test://test/locations/v1/postalcodes/US/search.json?apikey=test&q=94105",
            ),
        ),
        Response(
            status_code=200,
            content=accuweather_current_conditions_response,
            request=Request(
                method="GET",
                url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
            ),
        ),
        Response(
            status_code=200,
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
async def test_get_location_no_location_returned(
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_location method returns None if the response content is not as
    expected.
    """
    country: str = "US"
    postal_code: str = "94105"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
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


@pytest.mark.asyncio
async def test_get_current_conditions(
    mocker: MockerFixture,
    accuweather: AccuweatherBackend,
    accuweather_current_conditions_response: bytes,
) -> None:
    """Test that the get_current_conditions method returns CurrentConditions."""
    expected_conditions: CurrentConditions = CurrentConditions(
        url=(
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/current-weather/"
            "39376_pc?lang=en-us"
        ),
        summary="Mostly cloudy",
        icon_id=6,
        temperature=Temperature(c=15.5, f=60),
    )
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        content=accuweather_current_conditions_response,
        request=Request(
            method="GET",
            url="test://test/currentconditions/v1/39376_PC.json?apikey=test",
        ),
    )

    conditions: Optional[CurrentConditions] = await accuweather.get_current_conditions(
        mock_client, location_key
    )

    assert conditions == expected_conditions


@pytest.mark.asyncio
async def test_get_current_conditions_no_current_conditions_returned(
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_current_conditions method returns None if the response content
    is not as expected.
    """
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
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
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_current_conditions method raises an appropriate exception in
    the event of an AccuWeather API error.
    """
    expected_error_value: str = "Unexpected current conditions response"
    location_key: str = "INVALID"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=400,
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
    accuweather: AccuweatherBackend,
    forecast_response_fixture: str,
) -> None:
    """Test that the get_forecast method returns a Forecast."""
    expected_forecast: Forecast = Forecast(
        url=(
            "http://www.accuweather.com/en/us/san-francisco-ca/94103/"
            "daily-weather-forecast/39376_pc?lang=en-us"
        ),
        summary="Pleasant Saturday",
        high=Temperature(f=70),
        low=Temperature(f=57),
    )
    location_key: str = "39376_PC"
    content: bytes = request.getfixturevalue(forecast_response_fixture)
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
        content=content,
        request=Request(
            method="GET",
            url="test://test/forecasts/v1/daily/1day/39376_PC.json?apikey=test",
        ),
    )

    forecast: Optional[Forecast] = await accuweather.get_forecast(
        mock_client, location_key
    )

    assert forecast == expected_forecast


@pytest.mark.asyncio
async def test_get_forecast_no_forecast_returned(
    mocker: MockerFixture, accuweather: AccuweatherBackend
) -> None:
    """Test that the get_forecast method returns None if the response content is not as
    expected.
    """
    location_key: str = "39376_PC"
    mock_client: Any = mocker.AsyncMock(spec=AsyncClient)
    mock_client.get.return_value = Response(
        status_code=200,
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
    "cache_inputs_by_location",
    [
        (Location(country="US", region="CA", city="San Francisco", dma=807), None),
        (
            Location(region="CA", city="San Francisco", dma=807, postal_code="94105"),
            None,
        ),
        (
            Location(
                country="US",
                region="CA",
                city="San Francisco",
                dma=807,
                postal_code="94105",
            ),
            b"US94105",
        ),
    ],
)
@pytest.mark.asyncio
async def test_cache_inputs_for_weather_report(
    accuweather: AccuweatherBackend,
    cache_inputs_by_location: tuple[Location, Optional[bytes]],
) -> None:
    """Test that `cache_inputs_for_weather_report` computes the correct cache inputs when
    given locations with various missing fields.
    """
    cache_inputs: Optional[bytes] = accuweather.cache_inputs_for_weather_report(
        cache_inputs_by_location[0]
    )
    assert cache_inputs == cache_inputs_by_location[1]
