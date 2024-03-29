"""A wrapper for AccuWeather API interactions."""
import asyncio
import datetime
import functools
import hashlib
import json
import logging
from enum import Enum
from typing import Any, Callable, NamedTuple

import aiodogstatsd
from dateutil import parser
from httpx import URL, AsyncClient, HTTPError, InvalidURL, Response
from pydantic import BaseModel, ValidationError

from merino.cache.protocol import CacheAdapter
from merino.config import settings
from merino.exceptions import BackendError, CacheAdapterError
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)

logger = logging.getLogger(__name__)

PARTNER_PARAM_ID: str | None = settings.accuweather.get("url_param_partner_code")
PARTNER_CODE: str | None = settings.accuweather.get("partner_code")

# The Lua script to fetch the location key, current condition, and forecast for
# a given country/postal code.
#
# Note:
#   - The script expects a JSON serialized string as the value of the location key,
#     the location key can be accessed via the `key` property.
#     See `self.process_location_response()` for more details
#   - The cache key for the country/postal code should be provided through `KEYS[1]`
#   - The cache key templates for current conditions and forecast should be provided
#     through `ARGV[1]` and `ARGV[2]`
#   - The placeholder for location key (i.e. `self.url_location_key_placeholder`)
#     is passed via `ARGV[3]`
#   - If the location key is present in the cache, it uses the key to fetch the current
#     conditions and forecast for that key in the cache. It returns a 3-element array
#     `[location_key, current_condition, forecast]`. The last two element can be `nil`
#     if they are not present in the cache
#   - If the location key is missing, it will return an empty array
LUA_SCRIPT_CACHE_BULK_FETCH: str = """
    local location_key = redis.call("GET", KEYS[1])

    if not location_key then
        return {}
    end

    local key = cjson.decode(location_key)["key"]
    local condition_key = string.gsub(ARGV[1], ARGV[3], key)
    local forecast_key = string.gsub(ARGV[2], ARGV[3], key)

    local current_conditions = redis.call("GET", condition_key)
    local forecast = redis.call("GET", forecast_key)

    return {location_key, current_conditions, forecast}
"""
SCRIPT_ID: str = "bulk_fetch"


class AccuweatherLocation(BaseModel):
    """Location model for response data from AccuWeather endpoints."""

    # Location key.
    key: str

    # Display name in local dialect set with language code in URL.
    # Default is US English (en-us).
    localized_name: str


class WeatherData(NamedTuple):
    """The triplet for weather data used internally."""

    location: AccuweatherLocation | None = None
    current_conditions: CurrentConditions | None = None
    forecast: Forecast | None = None


class AccuweatherError(BackendError):
    """Error during interaction with the AccuWeather API."""


class WeatherDataType(Enum):
    """Enum to capture all types for weather data."""

    CURRENT_CONDITIONS = 1
    FORECAST = 2


class AccuweatherBackend:
    """Backend that connects to the AccuWeather API."""

    api_key: str
    cache: CacheAdapter
    cached_location_key_ttl_sec: int
    cached_current_condition_ttl_sec: int
    cached_forecast_ttl_sec: int
    metrics_client: aiodogstatsd.Client
    url_param_api_key: str
    url_postalcodes_path: str
    url_postalcodes_param_query: str
    url_current_conditions_path: str
    url_forecasts_path: str
    url_location_key_placeholder: str
    http_client: AsyncClient

    def __init__(
        self,
        api_key: str,
        cache: CacheAdapter,
        cached_location_key_ttl_sec: int,
        cached_current_condition_ttl_sec: int,
        cached_forecast_ttl_sec: int,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        url_param_api_key: str,
        url_postalcodes_path: str,
        url_postalcodes_param_query: str,
        url_current_conditions_path: str,
        url_forecasts_path: str,
        url_location_key_placeholder: str,
    ) -> None:
        """Initialize the AccuWeather backend.

        Raises:
            ValueError: If API key or URL parameters are None or empty.
        """
        if not api_key:
            raise ValueError("AccuWeather API key not specified")

        if (
            not url_param_api_key
            or not url_postalcodes_path
            or not url_postalcodes_param_query
            or not url_current_conditions_path
            or not url_forecasts_path
            or not url_location_key_placeholder
        ):
            raise ValueError("One or more AccuWeather API URL parameters are undefined")

        self.api_key = api_key
        self.cache = cache
        # This registration is lazy (i.e. no interaction with Redis) and infallible.
        self.cache.register_script(SCRIPT_ID, LUA_SCRIPT_CACHE_BULK_FETCH)
        self.cached_location_key_ttl_sec = cached_location_key_ttl_sec
        self.cached_current_condition_ttl_sec = cached_current_condition_ttl_sec
        self.cached_forecast_ttl_sec = cached_forecast_ttl_sec
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.url_param_api_key = url_param_api_key
        self.url_postalcodes_path = url_postalcodes_path
        self.url_postalcodes_param_query = url_postalcodes_param_query
        self.url_current_conditions_path = url_current_conditions_path
        self.url_forecasts_path = url_forecasts_path
        self.url_location_key_placeholder = url_location_key_placeholder

    def cache_key_for_accuweather_request(
        self, url: str, query_params: dict[str, str] = {}
    ) -> str:
        """Get the cache key for the accuweather request.
        Also ensure that the API key is stripped out.
        """
        min_params_for_cache_key = 1 if query_params.get(self.url_param_api_key) else 0
        if len(query_params) > min_params_for_cache_key:
            hasher = hashlib.blake2s()
            for key, value in sorted(query_params.items()):
                if key != self.url_param_api_key:
                    hasher.update(key.encode("utf-8") + value.encode("utf-8"))
            extra_identifiers = hasher.hexdigest()

            return f"{self.__class__.__name__}:v3:{url}:{extra_identifiers}"

        return f"{self.__class__.__name__}:v3:{url}"

    @functools.cache
    def cache_key_template(self, dt: WeatherDataType) -> str:
        """Get the cache key template for weather data."""
        query_params: dict[str, str] = {self.url_param_api_key: self.api_key}
        match dt:
            case WeatherDataType.CURRENT_CONDITIONS:
                return self.cache_key_for_accuweather_request(
                    self.url_current_conditions_path,
                    query_params=query_params,
                )
            case WeatherDataType.FORECAST:  # pragma: no cover
                return self.cache_key_for_accuweather_request(
                    self.url_forecasts_path,
                    query_params=query_params,
                )

    async def get_request(
        self,
        url_path: str,
        params: dict[str, str],
        process_api_response: Callable[[Any], dict[str, Any] | None],
        cache_ttl_sec: int,
    ) -> dict[str, Any] | None:
        """Get API response. Attempt to get it from cache first,
        then actually make the call if there's a cache miss.
        """
        cache_key = self.cache_key_for_accuweather_request(url_path, params)
        response_dict: dict[str, str] | None

        # The top level path in the URL gives us a good enough idea of what type of request
        # we are calling from here.
        request_type: str = url_path.strip("/").split("/", 1)[0]

        with self.metrics_client.timeit(f"accuweather.request.{request_type}.get"):
            response: Response = await self.http_client.get(url_path, params=params)
            response.raise_for_status()

        if (response_dict := process_api_response(response.json())) is None:
            self.metrics_client.increment(
                f"accuweather.request.{request_type}.processor.error"
            )
            return None

        response_expiry: str = response.headers.get("Expires")
        try:
            await self.store_request_into_cache(
                cache_key, response_dict, response_expiry, cache_ttl_sec
            )
        except (CacheAdapterError, ValueError) as exc:
            logger.error(f"Error with storing Accuweather to cache: {exc}")
            error_type = (
                "set_error" if isinstance(exc, CacheAdapterError) else "ttl_date_error"
            )
            self.metrics_client.increment(f"accuweather.cache.store.{error_type}")
            raise AccuweatherError(
                "Something went wrong with storing to cache. Did not update cache."
            )

        return response_dict

    async def store_request_into_cache(
        self,
        cache_key: str,
        response_dict: dict[str, Any],
        response_expiry: str,
        cache_ttl_sec: int,
    ):
        """Store the request into cache. Also ensures that the cache ttl is
        at least `cached_ttl_sec`.
        """
        with self.metrics_client.timeit("accuweather.cache.store"):
            expiry_delta: datetime.timedelta = parser.parse(
                response_expiry
            ) - datetime.datetime.now(datetime.timezone.utc)
            cache_ttl: datetime.timedelta = max(
                expiry_delta, datetime.timedelta(seconds=cache_ttl_sec)
            )
            cache_value = json.dumps(response_dict).encode("utf-8")
            await self.cache.set(cache_key, cache_value, ttl=cache_ttl)

    def emit_cache_fetch_metrics(self, cached_data: list[bytes | None]) -> None:
        """Emit cache fetch metrics.

        Params:
            - `cached_data` {list[bytes]} A list of bytes for location_key,
              current_condition, forecast
        """
        location, current, forecast = False, False, False
        match cached_data:
            case []:
                pass
            case [location_cached, current_cached, forecast_cached]:
                location, current, forecast = (
                    location_cached is not None,
                    current_cached is not None,
                    forecast_cached is not None,
                )
            case _:  # pragma: no cover
                pass

        self.metrics_client.increment(
            "accuweather.cache.hit.locations"
            if location
            else "accuweather.cache.fetch.miss.locations"
        )
        self.metrics_client.increment(
            "accuweather.cache.hit.currentconditions"
            if current
            else "accuweather.cache.fetch.miss.currentconditions"
        )
        self.metrics_client.increment(
            "accuweather.cache.hit.forecasts"
            if forecast
            else "accuweather.cache.fetch.miss.forecasts"
        )

    def parse_cached_data(self, cached_data: list[bytes | None]) -> WeatherData:
        """Parse the weather data from cache.

        Upon parsing errors, it will return the successfully parsed data thus far.

        Params:
            - `cached_data` {list[bytes]} A list of bytes for location_key,
              current_conditions, forecast
        """
        if len(cached_data) == 0:
            return WeatherData()

        location_cached, current_cached, forecast_cached = cached_data

        location: AccuweatherLocation | None = None
        current_conditions: CurrentConditions | None = None
        forecast: Forecast | None = None

        try:
            if location_cached is not None:
                location = AccuweatherLocation.model_validate_json(location_cached)
            if current_cached is not None:
                current_conditions = CurrentConditions.model_validate_json(
                    current_cached
                )
            if forecast_cached is not None:
                forecast = Forecast.model_validate_json(forecast_cached)
        except ValidationError as exc:
            logger.error(f"Failed to load weather report data from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.data.error")

        return WeatherData(location, current_conditions, forecast)

    def get_location_key_query_params(self, postal_code: str) -> dict[str, str]:
        """Get the query parameters for the location key for a given postal code."""
        return {
            self.url_param_api_key: self.api_key,
            self.url_postalcodes_param_query: postal_code,
        }

    async def get_weather_report(self, geolocation: Location) -> WeatherReport | None:
        """Get weather information from AccuWeather.

        Firstly, it will look up the Redis cache for the location key, current condition,
        and forecast. If all of them are found in the cache, then return them without
        requesting those from AccuWeather. Otherwise, it will issue API requests to
        AccuWeather for the missing data. Lastly, the API responses are stored in the
        cache for future uses.

        Note:
            - To avoid making excessive API requests to Accuweather in the event of
              "Cache Avalanche", it will *not* call AccuWeather for weather reports upon any
              cache errors such as timeouts or connection issues to Redis

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        """
        country: str | None = geolocation.country
        postal_code: str | None = geolocation.postal_code
        if not country or not postal_code:
            raise AccuweatherError("Country and/or postal code unknown")

        cache_key: str = self.cache_key_for_accuweather_request(
            self.url_postalcodes_path.format(country_code=country),
            query_params=self.get_location_key_query_params(postal_code),
        )
        # Look up for all the weather data from the cache.
        try:
            with self.metrics_client.timeit("accuweather.cache.fetch"):
                cached_data: list[bytes | None] = await self.cache.run_script(
                    sid=SCRIPT_ID,
                    keys=[cache_key],
                    # The order matters below. See `LUA_SCRIPT_CACHE_BULK_FETCH` for details.
                    args=[
                        self.cache_key_template(WeatherDataType.CURRENT_CONDITIONS),
                        self.cache_key_template(WeatherDataType.FORECAST),
                        self.url_location_key_placeholder,
                    ],
                )
        except CacheAdapterError as exc:
            logger.error(f"Failed to fetch weather report from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.fetch.error")
            return None

        self.emit_cache_fetch_metrics(cached_data)

        cached_report = self.parse_cached_data(cached_data)
        return await self.make_weather_report(cached_report, country, postal_code)

    async def make_weather_report(
        self,
        cached_report: WeatherData,
        country: str,
        postal_code: str,
    ) -> WeatherReport | None:
        """Make a `WeatherReport` either using the cached data or fetching from AccuWeather.

        Raises:
            AccuWeatherError: Failed request or 4xx and 5xx response from AccuWeather.
        """

        async def as_awaitable(val: Any) -> Any:
            """Wrap a non-awaitable value into a coroutine and resolve it right away."""
            return val

        location, current_conditions, forecast = cached_report

        if location and current_conditions and forecast:
            # Everything is ready, just return them.
            return WeatherReport(
                city_name=location.localized_name,
                current_conditions=current_conditions,
                forecast=forecast,
            )

        # The cached report is incomplete, now fetching from AccuWeather.
        if location is None:
            if (location := await self.get_location(country, postal_code)) is None:
                return None

        try:
            async with asyncio.TaskGroup() as tg:
                task_current = (
                    tg.create_task(self.get_current_conditions(location.key))
                    if current_conditions is None
                    else as_awaitable(current_conditions)
                )
                task_forecast = (
                    tg.create_task(self.get_forecast(location.key))
                    if forecast is None
                    else as_awaitable(forecast)
                )
        except ExceptionGroup as e:
            raise AccuweatherError(f"Failed to fetch weather report: {e.exceptions}")

        current_conditions = await task_current
        forecast = await task_forecast

        return (
            WeatherReport(
                city_name=location.localized_name,
                current_conditions=current_conditions,
                forecast=forecast,
            )
            if current_conditions and forecast
            else None
        )

    async def get_location(
        self, country: str, postal_code: str
    ) -> AccuweatherLocation | None:
        """Return location data for a specific country and postal code or None if
        location data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-locations-api/apis/get/locations/v1/postalcodes/{countryCode}/search
        """
        try:
            response: dict[str, Any] | None = await self.get_request(
                self.url_postalcodes_path.format(country_code=country),
                params=self.get_location_key_query_params(postal_code),
                process_api_response=process_location_response,
                cache_ttl_sec=self.cached_location_key_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected location response") from error

        return AccuweatherLocation(**response) if response else None

    async def get_current_conditions(
        self, location_key: str
    ) -> CurrentConditions | None:
        """Return current conditions data for a specific location or None if current
        conditions data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-current-conditions-api/apis/get/currentconditions/v1/{locationKey}
        """
        try:
            response: dict[str, Any] | None = await self.get_request(
                self.url_current_conditions_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
                process_api_response=process_current_condition_response,
                cache_ttl_sec=self.cached_current_condition_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected current conditions response") from error

        return (
            CurrentConditions(
                url=response["url"],
                summary=response["summary"],
                icon_id=response["icon_id"],
                temperature=Temperature(**response["temperature"]),
            )
            if response
            else None
        )

    async def get_forecast(self, location_key: str) -> Forecast | None:
        """Return daily forecast data for a specific location or None if daily
        forecast data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-forecast-api/apis/get/forecasts/v1/daily/1day/{locationKey}
        """
        try:
            response: dict[str, Any] | None = await self.get_request(
                self.url_forecasts_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
                process_api_response=process_forecast_response,
                cache_ttl_sec=self.cached_forecast_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected forecast response") from error

        return (
            Forecast(
                url=response["url"],
                summary=response["summary"],
                high=Temperature(**response["high"]),
                low=Temperature(**response["low"]),
            )
            if response
            else None
        )

    async def shutdown(self) -> None:
        """Close out the cache during shutdown."""
        await self.http_client.aclose()
        await self.cache.close()


def add_partner_code(
    url: str, url_param_id: str | None = None, partner_code: str | None = None
) -> str:
    """Add the partner code to the given URL."""
    if not url_param_id or not partner_code:
        return url

    try:
        parsed_url = URL(url)
        return str(parsed_url.copy_add_param(url_param_id, partner_code))
    except InvalidURL:  # pragma: no cover
        return url


def process_location_response(response: Any) -> dict[str, Any] | None:
    """Process the API response for location keys.

    Note that if you change the return format, ensure you update `LUA_SCRIPT_CACHE_BULK_FETCH`
    to reflect the change(s) here.
    """
    match response:
        case [
            {
                "Key": key,
                "LocalizedName": localized_name,
            },
        ]:
            # `type: ignore` is necessary because mypy gets confused when
            # matching structures of type `Any` and reports the following
            # line as unreachable. See
            # https://github.com/python/mypy/issues/12770
            return {  # type: ignore
                "key": key,
                "localized_name": localized_name,
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
