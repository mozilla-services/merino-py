# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather backend utils."""

from typing import Any

import pytest

from merino.middleware.geolocation import Coordinates, Location
from merino.providers.suggest.weather.backends.accuweather.utils import (
    get_lat_long_distance,
    get_closest_location_by_distance,
    process_location_response_with_country,
)
from merino.providers.suggest.weather.backends.protocol import WeatherContext


@pytest.fixture(name="location_response")
def fixture_location_response():
    """Location Response to Testing."""
    return [
        {
            "Version": 1,
            "Key": "282828",
            "Type": "City",
            "Rank": 85,
            "LocalizedName": "North Park",
            "EnglishName": "North Park",
            "PrimaryPostalCode": "V8T",
            "Region": {
                "ID": "NAM",
                "LocalizedName": "North America",
                "EnglishName": "North America",
            },
            "Country": {"ID": "CA", "LocalizedName": "Canada", "EnglishName": "Canada"},
            "AdministrativeArea": {
                "ID": "BC",
                "LocalizedName": "British Columbia",
                "EnglishName": "British Columbia",
                "Level": 1,
                "LocalizedType": "Province",
                "EnglishType": "Province",
                "CountryID": "CA",
            },
            "TimeZone": {
                "Code": "PST",
                "Name": "America/Vancouver",
                "GmtOffset": -8.0,
                "IsDaylightSaving": False,
                "NextOffsetChange": "2025-03-09T10:00:00Z",
            },
            "GeoPosition": {
                "Latitude": 48.431,
                "Longitude": -123.361,
                "Elevation": {
                    "Metric": {"Value": 11.0, "Unit": "m", "UnitType": 5},
                    "Imperial": {"Value": 36.0, "Unit": "ft", "UnitType": 0},
                },
            },
            "IsAlias": False,
            "ParentCity": {"Key": "47163", "LocalizedName": "Victoria", "EnglishName": "Victoria"},
            "SupplementalAdminAreas": [
                {"Level": 2, "LocalizedName": "Capital", "EnglishName": "Capital"}
            ],
            "DataSets": [
                "AirQualityCurrentConditions",
                "AirQualityForecasts",
                "Alerts",
                "ForecastConfidence",
                "FutureRadar",
                "MinuteCast",
                "Radar",
                "TidalForecast",
            ],
        },
        {
            "Version": 1,
            "Key": "888888",
            "Type": "City",
            "Rank": 85,
            "LocalizedName": "North Park",
            "EnglishName": "North Park",
            "PrimaryPostalCode": "S7K",
            "Region": {
                "ID": "NAM",
                "LocalizedName": "North America",
                "EnglishName": "North America",
            },
            "Country": {"ID": "CA", "LocalizedName": "Canada", "EnglishName": "Canada"},
            "AdministrativeArea": {
                "ID": "SK",
                "LocalizedName": "Saskatchewan",
                "EnglishName": "Saskatchewan",
                "Level": 1,
                "LocalizedType": "Province",
                "EnglishType": "Province",
                "CountryID": "CA",
            },
            "TimeZone": {
                "Code": "CST",
                "Name": "America/Regina",
                "GmtOffset": -6.0,
                "IsDaylightSaving": False,
                "NextOffsetChange": None,
            },
            "GeoPosition": {
                "Latitude": 52.145,
                "Longitude": -106.652,
                "Elevation": {
                    "Metric": {"Value": 454.0, "Unit": "m", "UnitType": 5},
                    "Imperial": {"Value": 1489.0, "Unit": "ft", "UnitType": 0},
                },
            },
            "IsAlias": False,
            "ParentCity": {
                "Key": "50338",
                "LocalizedName": "Saskatoon",
                "EnglishName": "Saskatoon",
            },
            "SupplementalAdminAreas": [],
            "DataSets": [
                "AirQualityCurrentConditions",
                "AirQualityForecasts",
                "Alerts",
                "ForecastConfidence",
                "FutureRadar",
                "MinuteCast",
                "Radar",
            ],
        },
    ]


@pytest.fixture(name="weather_context")
def fixture_weather_context():
    """Coordinate object for testing."""
    return WeatherContext(
        Location(coordinates=Coordinates(latitude=48.4308, longitude=-123.3586)),
        languages=["en-US"],
    )


@pytest.fixture(name="expected_location_results")
def fixture_expected_location_results():
    """Location Results for testing."""
    return {
        "administrative_area_id": "BC",
        "key": "282828",
        "localized_name": "North Park",
    }


def test_get_lat_long_distance():
    """Test distance calculate between two coordinates."""
    lat1 = 49.2827
    long1 = -123.120
    lat2 = 43.6532
    long2 = -79.3832
    assert 3358 == int(get_lat_long_distance(lat1, long1, lat2, long2))


def test_get_closest_location_by_distance(
    weather_context: WeatherContext,
    location_response: list[dict[str, Any]],
    expected_location_results: dict[str, Any],
):
    """Test retrieval of the closest location for a given Coordinate."""
    assert expected_location_results == get_closest_location_by_distance(
        location_response, weather_context
    )
    assert weather_context.distance_calculation is True


def test_get_closest_location_by_distance_does_not_update_distance_calc_when_no_location(
    weather_context: WeatherContext,
    expected_location_results: dict[str, Any],
):
    """When no locations are provided, distance_calculation should stay Nqone."""
    get_closest_location_by_distance([], weather_context)
    assert weather_context.distance_calculation is None


def test_process_location_response_with_country(
    weather_context: WeatherContext,
    location_response: dict[str, Any],
    expected_location_results: dict[str, Any],
):
    """Test location response with multiple locations are handled correctly."""
    assert expected_location_results == process_location_response_with_country(
        weather_context, location_response
    )
    assert weather_context.distance_calculation is True
