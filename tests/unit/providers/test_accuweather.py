# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi import APIRouter, FastAPI
from pytest import LogCaptureFixture

from merino.config import settings
from merino.middleware.geolocation import Location
from merino.providers.accuweather import Provider, Suggestion
from merino.providers.base import SuggestionRequest

default_location_body = [
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

default_forecast_body = {
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
            "Temperature": {
                "Minimum": {"Value": 57.0, "Unit": "F", "UnitType": 18},
                "Maximum": {"Value": 70.0, "Unit": "F", "UnitType": 18},
            },
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

app = FastAPI()
router = APIRouter()
location_body = default_location_body
forecast_body = default_forecast_body


def set_response_bodies(
    location: dict = default_location_body, forecast: dict = default_forecast_body
):
    global location_body
    global forecast_body
    location_body = location
    forecast_body = forecast


@router.get("/locations/v1/postalcodes/US/search.json")
async def locations_postalcodes_search():
    return location_body


@router.get("/forecasts/v1/daily/1day/39376_PC.json")
async def forecasts_daily_1day():
    return forecast_body


app.include_router(router)


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        region="CA",
        city="San Francisco",
        dma=807,
        postal_code="94105",
    )


@pytest.fixture(name="accuweather")
def fixture_accuweather() -> Provider:
    """Return an AccuWeather provider."""
    return Provider(app)


def test_enabled_by_default(accuweather: Provider) -> None:
    """Test for the enabled_by_default method."""

    assert accuweather.enabled_by_default is False


def test_hidden(accuweather: Provider) -> None:
    """Test for the hidden method."""

    assert accuweather.hidden() is False


@pytest.mark.asyncio
async def test_forecast_returned(accuweather: Provider, geolocation: Location) -> None:
    """Test for a successful query."""

    set_response_bodies()

    res = await accuweather.query(SuggestionRequest(query="", geolocation=geolocation))
    assert res == [
        Suggestion(
            title="Forecast",
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?day=1&lang=en-us"
            ),
            provider="accuweather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name="San Francisco",
            temperature_unit="F",
            high=70.0,
            low=57.0,
            day_summary="Clear",
            day_precipitation=False,
            night_summary="Intermittent clouds",
            night_precipitation=True,
        )
    ]


@pytest.mark.asyncio
async def test_no_location_returned(
    accuweather: Provider, geolocation: Location
) -> None:
    """Test for a query that doesn't return a location."""

    set_response_bodies(location=[])

    res = await accuweather.query(SuggestionRequest(query="", geolocation=geolocation))
    assert res == []


@pytest.mark.asyncio
async def test_no_forecast_returned(
    accuweather: Provider, geolocation: Location
) -> None:
    """Test for a query that doesn't return a forecast for a valid location."""

    set_response_bodies(forecast={})

    res = await accuweather.query(SuggestionRequest(query="", geolocation=geolocation))
    assert res == []


@pytest.mark.asyncio
async def test_invalid_location_key(
    accuweather: Provider, geolocation: Location
) -> None:
    """Test for a query that doesn't return a forecast due to an invalid
    location key."""

    set_response_bodies(
        forecast={
            "Code": "400",
            "Message": "LocationKey is invalid: bogus",
            "Reference": "/forecasts/v1/daily/1day/bogus.json",
        }
    )

    res = await accuweather.query(SuggestionRequest(query="", geolocation=geolocation))
    assert res == []


@pytest.mark.parametrize(
    "geolocation",
    [
        Location(postal_code=94105),
        Location(country="US", region="CA", city="Some City", dma=555),
        Location(),
    ],
)
@pytest.mark.asyncio
async def test_no_client_country_or_postal_code(
    caplog: LogCaptureFixture, accuweather: Provider, geolocation: Location
):
    """Test that if a client has an unknown country or postal code, that a
    warning is logged and no suggestions are returned."""
    set_response_bodies()

    res = await accuweather.query(SuggestionRequest(query="", geolocation=geolocation))

    assert res == []
    assert len(caplog.messages) == 1
    assert caplog.messages[0] == "Country and/or postal code unknown"
