"""Unit tests for AccuWeather utility methods."""

from pydantic.networks import HttpUrl
import pytest
from typing import Any

from merino.providers.suggest.weather.backends.accuweather.utils import (
    add_partner_code,
    process_hourly_forecast_response,
    create_hourly_forecasts_from_json,
    PARTNER_CODE_NEWTAB,
    PARTNER_PARAM_ID,
)
from merino.providers.suggest.weather.backends.protocol import HourlyForecast, Temperature


@pytest.fixture(name="accuweather_hourly_forecasts_response")
def fixture_accuweather_hourly_forecasts_response() -> list[dict[str, Any]]:
    """Return the Accuweather hourly forecasts API response.
    NOTE: The actual endpoint returns 12 list items, this one is truncated to 6 items for testing only.
    """
    return [
        {
            "DateTime": "2026-01-28T13:00:00-06:00",
            "EpochDateTime": 1769626800,
            "WeatherIcon": 3,
            "IconPhrase": "Partly sunny",
            "HasPrecipitation": "false",
            "IsDaylight": "true",
            "Temperature": {"Value": 30.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=13&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=13&lang=en-us",
        },
        {
            "DateTime": "2026-01-28T14:00:00-06:00",
            "EpochDateTime": 1769630400,
            "WeatherIcon": 2,
            "IconPhrase": "Mostly sunny",
            "HasPrecipitation": "false",
            "IsDaylight": "true",
            "Temperature": {"Value": 31.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=14&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=14&lang=en-us",
        },
        {
            "DateTime": "2026-01-28T15:00:00-06:00",
            "EpochDateTime": 1769634000,
            "WeatherIcon": 2,
            "IconPhrase": "Mostly sunny",
            "HasPrecipitation": "false",
            "IsDaylight": "true",
            "Temperature": {"Value": 32.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=15&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=15&lang=en-us",
        },
        {
            "DateTime": "2026-01-28T16:00:00-06:00",
            "EpochDateTime": 1769637600,
            "WeatherIcon": 2,
            "IconPhrase": "Mostly sunny",
            "HasPrecipitation": "false",
            "IsDaylight": "true",
            "Temperature": {"Value": 30.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=16&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=16&lang=en-us",
        },
        {
            "DateTime": "2026-01-28T17:00:00-06:00",
            "EpochDateTime": 1769641200,
            "WeatherIcon": 2,
            "IconPhrase": "Mostly sunny",
            "HasPrecipitation": "false",
            "IsDaylight": "true",
            "Temperature": {"Value": 27.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=17&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=17&lang=en-us",
        },
        {
            "DateTime": "2026-01-28T18:00:00-06:00",
            "EpochDateTime": 1769644800,
            "WeatherIcon": 34,
            "IconPhrase": "Mostly clear",
            "HasPrecipitation": "false",
            "IsDaylight": "false",
            "Temperature": {"Value": 24.0, "Unit": "F", "UnitType": 18},
            "PrecipitationProbability": 0,
            "MobileLink": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=18&lang=en-us",
            "Link": "http://www.accuweather.com/en/us/st-louis-mo/63102/hourly-weather-forecast/349084?day=1&hbhhour=18&lang=en-us",
        },
    ]


@pytest.fixture(name="accuweather_hourly_forecasts_processed_response")
def fixture_accuweather_hourly_forecasts_processed_response(
    accuweather_hourly_forecasts_response: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Return 5 (DEFAULT_FORECAST_HOURS) of the processed version of accuweather_hourly_forecasts_response fixture above."""
    return {
        "hourly_forecasts": [
            {
                "date_time": forecast["DateTime"],
                "epoch_date_time": forecast["EpochDateTime"],
                "temperature_unit": forecast["Temperature"]["Unit"].lower(),
                "temperature_value": forecast["Temperature"]["Value"],
                "icon_id": forecast["WeatherIcon"],
                "url": add_partner_code(forecast["Link"], PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB),
            }
            for forecast in accuweather_hourly_forecasts_response[
                :5
            ]  # this is the DEFAULT_FORECAST_HOURS
        ]
    }


@pytest.fixture(name="accuweather_hourly_forecasts")
def fixture_accuweather_hourly_forecasts(
    accuweather_hourly_forecasts_response,
) -> list[HourlyForecast]:
    """Create a list of two HourlyForecast objects from the first two accuweather_hourly_forecasts_response items."""
    first_hourly_forecast = accuweather_hourly_forecasts_response[0]
    second_hourly_forecast = accuweather_hourly_forecasts_response[1]

    return [
        HourlyForecast(
            date_time=first_hourly_forecast["DateTime"],
            epoch_date_time=first_hourly_forecast["EpochDateTime"],
            temperature=Temperature(f=first_hourly_forecast["Temperature"]["Value"]),
            icon_id=first_hourly_forecast["WeatherIcon"],
            url=HttpUrl(
                add_partner_code(
                    first_hourly_forecast["Link"], PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB
                )
            ),
        ),
        HourlyForecast(
            date_time=second_hourly_forecast["DateTime"],
            epoch_date_time=second_hourly_forecast["EpochDateTime"],
            temperature=Temperature(f=second_hourly_forecast["Temperature"]["Value"]),
            icon_id=second_hourly_forecast["WeatherIcon"],
            url=HttpUrl(
                add_partner_code(
                    second_hourly_forecast["Link"], PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB
                )
            ),
        ),
    ]


def test_process_hourly_forecast_response(
    accuweather_hourly_forecasts_response: list[dict[str, Any]],
    accuweather_hourly_forecasts_processed_response: dict[str, list[dict[str, Any]]],
) -> None:
    """Test process_hourly_forecast_response with various inputs."""
    # test for None
    assert process_hourly_forecast_response(None) is None

    # test for non list
    assert process_hourly_forecast_response({}) is None

    # test for empty list
    assert process_hourly_forecast_response([]) == {"hourly_forecasts": []}

    # test for valid api response - should return first 5 forecasts (DEFAULT_FORECAST_HOURS)
    actual = process_hourly_forecast_response(accuweather_hourly_forecasts_response)
    expected = accuweather_hourly_forecasts_processed_response

    assert actual is not None
    assert "hourly_forecasts" in actual
    assert len(actual["hourly_forecasts"]) == 5  # Limited to DEFAULT_FORECAST_HOURS
    assert actual == expected


def test_create_hourly_forecasts_from_json(
    accuweather_hourly_forecasts_processed_response: dict[str, list[dict[str, Any]]],
    accuweather_hourly_forecasts: list[HourlyForecast],
) -> None:
    """Test create_hourly_forecasts_from_json method with various inputs."""
    # test for empty list
    assert create_hourly_forecasts_from_json([]) == []

    # test for two valid hourly forecast json objects
    actual = create_hourly_forecasts_from_json(
        accuweather_hourly_forecasts_processed_response["hourly_forecasts"][:2]
    )
    expected = accuweather_hourly_forecasts
    assert actual == expected
