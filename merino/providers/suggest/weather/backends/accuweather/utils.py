"""Utilities for the AccuWeather backend."""

import logging
from enum import StrEnum
from typing import Any, TypedDict

from httpx import URL, InvalidURL
from pydantic import HttpUrl

from merino.configs import settings
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    HourlyForecast,
    Temperature,
)

PARTNER_PARAM_ID: str | None = settings.accuweather.get("url_param_partner_code")
PARTNER_CODE_NEWTAB: str | None = settings.accuweather.get("partner_code_newtab_value")
PARTNER_FFSUGGEST_CODE: str | None = settings.accuweather.get("partner_code_ffsuggest_value")
VALID_LANGUAGES: frozenset = frozenset(settings.accuweather.default_languages)
DEFAULT_FORECAST_HOURS = 5

logger = logging.getLogger(__name__)


class RequestType(StrEnum):
    """Enum for the request types to AccuWeather's API endpoints.

    It usually maps to the first component of the URL path of the underlying API URL.
    """

    LOCATIONS = "locations"
    CURRENT_CONDITIONS = "currentconditions"
    FORECASTS = "forecasts"
    HOURLY_FORECASTS = "hourlyforecasts"
    AUTOCOMPLETE = "autocomplete"


class ProcessedLocationResponse(TypedDict):
    """Class for response keys and values processed from Accuweather location requests."""

    key: str
    localized_name: str
    administrative_area_id: str
    country_name: str


def add_partner_code(
    url: str, url_param_id: str | None = None, partner_code: str | None = None
) -> str:
    """Add the partner code to the given URL."""
    # reformat the http url returned for current conditions and forecast to https
    https_url = url if url.startswith("https:") else url.replace("http:", "https:", 1)

    if not url_param_id or not partner_code:
        return https_url

    try:
        parsed_url = URL(https_url)
        return str(parsed_url.copy_add_param(url_param_id, partner_code))
    except InvalidURL:  # pragma: no cover
        return url


def process_location_completion_response(response: Any) -> list[dict[str, Any]] | None:
    """Process the API response for location completion request."""
    if response is None or not isinstance(response, list):
        return None

    return [
        {
            "key": location["Key"],
            "rank": location["Rank"],
            "type": location["Type"],
            "localized_name": location["LocalizedName"],
            "country": {
                "id": location["Country"]["ID"],
                "localized_name": location["Country"]["LocalizedName"],
            },
            "administrative_area": {
                "id": location["AdministrativeArea"]["ID"],
                "localized_name": location["AdministrativeArea"]["LocalizedName"],
            },
        }
        for location in response
    ]


def process_location_response(
    response: Any,
) -> ProcessedLocationResponse | None:
    """Process the API response for location keys.

    Note that if you change the return format, ensure you update `LUA_SCRIPT_CACHE_BULK_FETCH`
    to reflect the change(s) here.
    """
    match response:
        case [
            {
                "Key": key,
                "LocalizedName": localized_name,
                "AdministrativeArea": {"ID": administrative_area_id},
                "Country": {
                    "LocalizedName": country_name,
                },
            },
            *_,
        ]:
            # `type: ignore` is necessary because mypy gets confused when
            # matching structures of type `Any` and reports the following
            # line as unreachable. See
            # https://github.com/python/mypy/issues/12770
            return {  # type: ignore
                "key": key,
                "localized_name": localized_name,
                "administrative_area_id": administrative_area_id,
                "country_name": country_name,
            }
        case _:
            return None


def process_current_condition_response(response: Any) -> dict[str, Any] | None:
    """Process the API response for current conditions."""
    match response:
        case [
            {
                "Link": url,
                "WeatherText": summary,
                "WeatherIcon": icon_id,
                "Temperature": {
                    "Metric": {
                        "Value": c,
                    },
                    "Imperial": {
                        "Value": f,
                    },
                },
            }
        ]:
            # `type: ignore` is necessary because mypy gets confused when
            # matching structures of type `Any` and reports the following
            # lines as unreachable. See
            # https://github.com/python/mypy/issues/12770
            url = add_partner_code(url, PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB)  # type: ignore
            return {
                "url": url,
                "summary": summary,
                "icon_id": icon_id,
                "temperature": {"c": c, "f": f},
            }
        case _:
            return None


def process_forecast_response(response: Any) -> dict[str, Any] | None:
    """Process the API response for forecasts."""
    match response:
        case {
            "Headline": {
                "Text": summary,
                "Link": url,
            },
            "DailyForecasts": [
                {
                    "Temperature": {
                        "Maximum": {
                            "Value": high_value,
                            "Unit": ("C" | "F") as high_unit,
                        },
                        "Minimum": {
                            "Value": low_value,
                            "Unit": ("C" | "F") as low_unit,
                        },
                    },
                }
            ],
        }:
            # `type: ignore` is necessary because mypy gets confused when
            # matching structures of type `Any` and reports the following
            # lines as unreachable. See
            # https://github.com/python/mypy/issues/12770
            url = add_partner_code(url, PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB)  # type: ignore

            return {
                "url": url,
                "summary": summary,
                "high": {high_unit.lower(): high_value},
                "low": {low_unit.lower(): low_value},
            }
        case _:
            return None


def process_hourly_forecast_response(response: Any) -> dict[str, list[dict[str, Any]]] | None:
    """Process the API response for hourly forecasts."""
    match response:
        case list():
            hourly_forecasts: list[dict[str, Any]] = []

            for forecast in response[:DEFAULT_FORECAST_HOURS]:
                url = add_partner_code(forecast["Link"], PARTNER_PARAM_ID, PARTNER_CODE_NEWTAB)
                temperature_unit = forecast["Temperature"]["Unit"].lower()
                temperature_value = forecast["Temperature"]["Value"]

                hourly_forecasts.append(
                    {
                        "date_time": forecast["DateTime"],
                        "epoch_date_time": forecast["EpochDateTime"],
                        "temperature_unit": temperature_unit,
                        "temperature_value": temperature_value,
                        "icon_id": forecast["WeatherIcon"],
                        "url": url,
                    }
                )

            return {"hourly_forecasts": hourly_forecasts}
        case _:
            return None


def create_hourly_forecasts_from_json(
    hourly_forecast_json: list[dict[str, Any]],
) -> list[HourlyForecast]:
    """Create and return a list of HourlyForecast objects from processed api response JSON."""
    valid_hourly_forecasts = []

    for forecast in hourly_forecast_json:
        temperature_unit = forecast["temperature_unit"]
        temperature_value = forecast["temperature_value"]
        temperature = None

        if temperature_unit == "c":
            temperature = Temperature(c=temperature_value)
        else:
            temperature = Temperature(f=temperature_value)

        hourly_forecast = HourlyForecast(
            date_time=forecast["date_time"],
            epoch_date_time=forecast["epoch_date_time"],
            temperature=temperature,
            icon_id=forecast["icon_id"],
            url=HttpUrl(forecast["url"]),
        )

        HourlyForecast.model_validate(hourly_forecast)

        valid_hourly_forecasts.append(hourly_forecast)

    return valid_hourly_forecasts


def get_language(requested_languages: list[str]) -> str:
    """Get first language that is in default_languages."""
    return next(
        (language for language in requested_languages if language in VALID_LANGUAGES), "en-US"
    )


def update_weather_url_with_suggest_partner_code(
    current_conditions: CurrentConditions, forecast: Forecast
) -> tuple[CurrentConditions, Forecast]:
    """Update weather model urls to use suggest partner code."""
    if not PARTNER_PARAM_ID:
        return current_conditions, forecast
    else:
        cc_modified_url = URL(str(current_conditions.url)).copy_set_param(
            PARTNER_PARAM_ID, PARTNER_FFSUGGEST_CODE
        )
        f_modified_url = URL(str(forecast.url)).copy_set_param(
            PARTNER_PARAM_ID, PARTNER_FFSUGGEST_CODE
        )
        current_conditions.url = HttpUrl(str(cc_modified_url))
        forecast.url = HttpUrl(str(f_modified_url))
        return current_conditions, forecast
