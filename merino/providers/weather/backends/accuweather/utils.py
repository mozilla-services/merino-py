"""Utilities for the AccuWeather backend."""

import math
from enum import StrEnum
from typing import Any, TypedDict

from httpx import URL, InvalidURL
from merino.configs.config import settings
from merino.middleware.geolocation import Coordinates

PARTNER_PARAM_ID: str | None = settings.accuweather.get("url_param_partner_code")
PARTNER_CODE: str | None = settings.accuweather.get("partner_code")
VALID_LANGUAGES: frozenset = frozenset(settings.accuweather.default_languages)
DISTANCE_THRESHOLD = 50  # 50 km


class RequestType(StrEnum):
    """Enum for the request types to AccuWeather's API endpoints.

    It usually maps to the first component of the URL path of the underlying API URL.
    """

    LOCATIONS = "locations"
    CURRENT_CONDITIONS = "currentconditions"
    FORECASTS = "forecasts"
    AUTOCOMPLETE = "autocomplete"


class ProcessedLocationResponse(TypedDict):
    """Class for response keys and values processed from Accuweather location requests."""

    key: str
    localized_name: str
    administrative_area_id: str


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


def process_location_response_with_country_and_region(
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
            }
        case _:
            return None


def process_location_response_with_country(
    coordinates: Coordinates | None, response: Any
) -> ProcessedLocationResponse | None:
    """Process the API response for a single location key from country code endpoint.

    Note that if you change the return format, ensure you update `LUA_SCRIPT_CACHE_BULK_FETCH`
    to reflect the change(s) here.
    """
    match response:
        case [
            {
                "Key": key,
                "LocalizedName": localized_name,
                "AdministrativeArea": {"ID": administrative_area_id},
            },
        ]:
            # `type: ignore` is necessary because mypy gets confused when
            # matching structures of type `Any` and reports the following
            # line as unreachable. See
            # https://github.com/python/mypy/issues/12770
            return {  # type: ignore
                "key": key,
                "localized_name": localized_name,
                "administrative_area_id": administrative_area_id,
            }
        case _:
            return get_closest_location_by_distance(response, coordinates)  # type: ignore


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
            url = add_partner_code(url, PARTNER_PARAM_ID, PARTNER_CODE)  # type: ignore
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
            url = add_partner_code(url, PARTNER_PARAM_ID, PARTNER_CODE)  # type: ignore

            return {
                "url": url,
                "summary": summary,
                "high": {high_unit.lower(): high_value},
                "low": {low_unit.lower(): low_value},
            }
        case _:
            return None


def get_language(requested_languages: list[str]) -> str:
    """Get first language that is in default_languages."""
    return next(
        (language for language in requested_languages if language in VALID_LANGUAGES), "en-US"
    )


def get_closest_location_by_distance(
    locations: list[dict[str, Any]], coordinates: Coordinates
) -> ProcessedLocationResponse | None:
    """Get the closest location by distance within the DISTANCE THRESHOLD."""
    closest_location = None
    min_distance = math.inf
    if coordinates:
        lat1 = coordinates.latitude
        long1 = coordinates.longitude

        if not lat1 or not long1:
            return None

        for location in locations:
            try:
                lat2 = location["GeoPosition"]["Latitude"]
                long2 = location["GeoPosition"]["Longitude"]

                d = get_lat_long_distance(lat1, long1, lat2, long2)
                if d < min_distance and d <= DISTANCE_THRESHOLD:
                    closest_location = location
                    min_distance = d
            except KeyError:
                continue

    if closest_location:
        try:
            return {
                "key": closest_location["Key"],
                "localized_name": closest_location["LocalizedName"],
                "administrative_area_id": closest_location["AdministrativeArea"]["ID"],
            }
        except KeyError:
            return None
    return None


def get_lat_long_distance(lat1: float, long1: float, lat2: float, long2: float) -> float:
    """Calculate distance between two coordinates via the Haversine formula."""
    lat1 = math.radians(lat1)
    long1 = math.radians(long1)

    lat2 = math.radians(lat2)
    long2 = math.radians(long2)

    d_lat = lat2 - lat1
    d_long = long2 - long1

    radicand = 1 - math.cos(d_lat) + (math.cos(lat1) * math.cos(lat2) * (1 - math.cos(d_long)))
    s9rt = math.sqrt(radicand / 2)
    # radius of the earth
    r = 6371

    return 2 * r * math.asin(s9rt)
