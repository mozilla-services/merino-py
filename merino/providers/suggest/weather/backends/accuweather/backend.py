"""A wrapper for AccuWeather API interactions."""

import asyncio
import datetime
import functools
import hashlib
import orjson
import logging
from enum import Enum
from typing import Any, Callable, NamedTuple, cast

import aiodogstatsd
from dateutil import parser
from httpx import AsyncClient, HTTPError, Response
from pydantic import BaseModel, ValidationError

from merino.cache.protocol import CacheAdapter
from merino.exceptions import CacheAdapterError
from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    set_region_mapping,
    increment_skip_cities_mapping,
)
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    LocationCompletion,
    Temperature,
    WeatherReport,
    WeatherContext,
    HourlyForecast,
)
from merino.providers.suggest.weather.backends.accuweather import pathfinder
from merino.providers.suggest.weather.backends.accuweather.utils import (
    RequestType,
    process_location_completion_response,
    process_forecast_response,
    process_hourly_forecast_response,
    process_current_condition_response,
    process_location_response,
    get_language,
    update_weather_url_with_suggest_partner_code,
)

from merino.providers.suggest.weather.backends.accuweather.errors import (
    AccuweatherError,
    AccuweatherErrorMessages,
    MissingLocationKeyError,
)

logger = logging.getLogger(__name__)

# The Lua script to fetch the location key, current condition, forecast, and a TTL for
# a given country/region/city.
#
# Note:
#   - The script expects a JSON serialized string as the value of the location key,
#     the location key can be accessed via the `key` property.
#     See `self.process_location_response()` for more details
#   - The cache key for the country/region/city should be provided through `KEYS[1]`
#   - The cache key templates for current conditions and forecast should be provided
#     through `ARGV[1]` and `ARGV[2]`
#   - The placeholder for location key (i.e. `self.url_location_key_placeholder`)
#     is passed via `ARGV[3]`
#   - If the location key is present in the cache, it uses the key to fetch the current
#     conditions and forecast for that key in the cache. It returns a 4-element array
#     `[location_key, current_condition, forecast, ttl]`. The `current_condition` and `forecast` are `nil`
#     if they are not present in the cache
#   - If the location key is missing, it will return an empty array
#   - If the current_conditions and forecast TTLs are a non-positive value (-1 or -2),
#     it will return ttl as false, which is translated to None type in app code.
LUA_SCRIPT_CACHE_BULK_FETCH: str = """
    local location_key = redis.call("GET", KEYS[1])

    if not location_key then
        return {}
    end

    local key = cjson.decode(location_key)["key"]
    local condition_key = string.gsub(ARGV[1], ARGV[4], key)
    local forecast_key = string.gsub(ARGV[2], ARGV[4], key)
    local hourly_forecast_key = string.gsub(ARGV[3], ARGV[4], key)

    local current_conditions = redis.call("GET", condition_key)
    local forecast = redis.call("GET", forecast_key)
    local hourly_forecast = redis.call("GET", hourly_forecast_key)
    local ttl = false

    if current_conditions and forecast then
        local current_conditions_ttl = redis.call("TTL", condition_key)
        local forecast_ttl = redis.call("TTL", forecast_key)
        ttl = math.min(current_conditions_ttl, forecast_ttl)
    end

    return {location_key, current_conditions, forecast, hourly_forecast, ttl}
"""
SCRIPT_ID_BULK_FETCH_VIA_GEOLOCATION: str = "bulk_fetch_by_geolocation"


# The Lua script to fetch the current condition, forecast, and a TTL for
# a given a city-based_location key.
#
# Note:
#   - The script retrieves the cached current conditions, forecast and TTL data
#   - The cache key for current conditions and forecast should be provided
#     through `ARGV[1]` and `ARGV[2]`
#   - It returns a 3-element array `[current_condition, forecast, ttl]`. All of these elements
#     can be nil
#   - If the forecast and current_conditions TTLs are a non-positive value (-1 or -2),
#     it will return ttl as false, which is translated to None type in app code.
LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION: str = """
    local condition_key = ARGV[1]
    local forecast_key = ARGV[2]

    local current_conditions = redis.call("GET", condition_key)
    local forecast = redis.call("GET", forecast_key)
    local ttl = false

    if current_conditions and forecast then
        local current_conditions_ttl = redis.call("TTL", condition_key)
        local forecast_ttl = redis.call("TTL", forecast_key)
        ttl = math.min(current_conditions_ttl, forecast_ttl)
    end

    return {current_conditions, forecast, ttl}
"""
SCRIPT_LOCATION_KEY_ID = "bulk_fetch_by_location_key"
# LOCATION_SENTINEL constant below is prepended to the list returned by the above
# bulk_fetch_by_location_key script. This is to accommodate parse_cached_data method which
# expects 4 list elements to be returned from the cache but this script only returns 3.
LOCATION_SENTINEL = None

ALIAS_PARAM: str = "alias"
ALIAS_PARAM_VALUE: str = "always"
LOCATION_COMPLETE_ALIAS_PARAM: str = "includealiases"
LOCATION_COMPLETE_ALIAS_PARAM_VALUE: str = "true"
LANGUAGE_PARAM: str = "language"
URLBAR_REQUEST_SOURCE: str = "urlbar"

__all__ = [
    "AccuweatherBackend",
    "AccuweatherError",
    "AccuweatherLocation",
    "CurrentConditionsWithTTL",
    "ForecastWithTTL",
    "HourlyForecastWithTTL",
    "WeatherData",
    "WeatherDataType",
]


class AccuweatherLocation(BaseModel):
    """Location model for response data from AccuWeather endpoints."""

    # Location key.
    key: str

    # Display name in local dialect set with language code in URL.
    # Default is US English (en-us).
    localized_name: str

    # Unique Administrative Area ID for the Location.
    administrative_area_id: str

    # Country name for the location
    country_name: str


class WeatherData(NamedTuple):
    """The quartet for weather data used internally."""

    location: AccuweatherLocation | None = None
    current_conditions: CurrentConditions | None = None
    forecast: Forecast | None = None
    hourly_forecast: list[HourlyForecast] | None = None
    ttl: int | None = None


class CurrentConditionsWithTTL(NamedTuple):
    """CurrentConditions and its TTL value that is used to build a WeatherReport instance"""

    current_conditions: CurrentConditions
    ttl: int


class ForecastWithTTL(NamedTuple):
    """Forecast and its TTL value that is used to build a WeatherReport instance"""

    forecast: Forecast
    ttl: int


class HourlyForecastWithTTL(NamedTuple):
    """Hourly Forecast and its TTL value that is used to build a WeatherReport instance"""

    hourly_forecast: list[HourlyForecast]
    ttl: int


class WeatherDataType(Enum):
    """Enum to capture all types for weather data."""

    CURRENT_CONDITIONS = 1
    FORECAST = 2
    HOURLY_FORECAST = 3


class AccuweatherBackend:
    """Backend that connects to the AccuWeather API using City to find location key."""

    api_key: str
    cache: CacheAdapter
    cached_location_key_ttl_sec: int
    cached_current_condition_ttl_sec: int
    cached_forecast_ttl_sec: int
    cached_hourly_forecast_ttl_sec: int
    metrics_client: aiodogstatsd.Client
    url_param_api_key: str
    url_cities_admin_path: str
    url_cities_path: str
    url_cities_param_query: str
    url_current_conditions_path: str
    url_forecasts_path: str
    url_hourly_forecasts_path: str
    url_location_path: str
    url_location_key_placeholder: str
    url_location_completion_path: str
    http_client: AsyncClient
    metrics_sample_rate: float

    def __init__(
        self,
        api_key: str,
        cache: CacheAdapter,
        cached_location_key_ttl_sec: int,
        cached_current_condition_ttl_sec: int,
        cached_forecast_ttl_sec: int,
        cached_hourly_forecast_ttl_sec: int,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        url_param_api_key: str,
        url_cities_admin_path: str,
        url_cities_path: str,
        url_cities_param_query: str,
        url_current_conditions_path: str,
        url_forecasts_path: str,
        url_hourly_forecasts_path: str,
        url_location_completion_path: str,
        url_location_key_placeholder: str,
        metrics_sample_rate: float,
    ) -> None:
        """Initialize the AccuWeather backend.

        Raises:
            ValueError: If API key or URL parameters are None or empty.
        """
        if not api_key:
            raise ValueError("AccuWeather API key not specified")

        if (
            not url_param_api_key
            or not url_cities_admin_path
            or not url_cities_path
            or not url_cities_param_query
            or not url_current_conditions_path
            or not url_forecasts_path
            or not url_hourly_forecasts_path
            or not url_location_key_placeholder
        ):
            raise ValueError("One or more AccuWeather API URL parameters are undefined")

        self.api_key = api_key
        self.cache = cache
        # This registration is lazy (i.e. no interaction with Redis) and infallible.
        self.cache.register_script(
            SCRIPT_LOCATION_KEY_ID, LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION
        )
        self.cache.register_script(
            SCRIPT_ID_BULK_FETCH_VIA_GEOLOCATION, LUA_SCRIPT_CACHE_BULK_FETCH
        )
        self.cached_location_key_ttl_sec = cached_location_key_ttl_sec
        self.cached_current_condition_ttl_sec = cached_current_condition_ttl_sec
        self.cached_forecast_ttl_sec = cached_forecast_ttl_sec
        self.cached_hourly_forecast_ttl_sec = cached_hourly_forecast_ttl_sec
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.url_param_api_key = url_param_api_key
        self.url_cities_admin_path = url_cities_admin_path
        self.url_cities_path = url_cities_path
        self.url_cities_param_query = url_cities_param_query
        self.url_current_conditions_path = url_current_conditions_path
        self.url_forecasts_path = url_forecasts_path
        self.url_hourly_forecasts_path = url_hourly_forecasts_path
        self.url_location_completion_path = url_location_completion_path
        self.url_location_key_placeholder = url_location_key_placeholder
        self.metrics_sample_rate = metrics_sample_rate

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

            return f"{self.__class__.__name__}:v7:{url}:{extra_identifiers}"

        return f"{self.__class__.__name__}:v7:{url}"

    @functools.cache
    def cache_key_template(self, dt: WeatherDataType, language: str) -> str:
        """Get the cache key template for weather data."""
        query_params: dict[str, str] = {
            self.url_param_api_key: self.api_key,
            LANGUAGE_PARAM: language,
        }
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
            case WeatherDataType.HOURLY_FORECAST:
                return self.cache_key_for_accuweather_request(
                    self.url_hourly_forecasts_path,
                    query_params=query_params,
                )

    async def request_upstream(
        self,
        url_path: str,
        params: dict[str, str],
        request_type: RequestType,
        process_api_response: Callable[[Any], Any | None],
        cache_ttl_sec: int = 0,
        should_cache: bool = True,
    ) -> Any | None:
        """Request the AccuWeather API and process the response. Optionally, the processed
        response can be stored in the cache.

        Params:
          - `url_path` {str}: the endpoint URL
          - `params` {dict}: the query parameters of the URL
          - `request_type` {RequestType}: the request type used for metrics and logging
          - `process_api_response` {Callable}: the response processor, it returns None if the processing fails
          - `cache_ttl_sec` {int}: the cache TTL in seconds
          - `should_cache` {bool}: whether to cache the processed response
        Return:
          - The processed response or None if failed
        Raises:
          - `HTTPError` upon HTTP request errors
          - `AccuweatherError` upon cache write errors
        """
        # increment the upstream request stat counter
        self.metrics_client.increment(f"accuweather.upstream.request.{request_type}.get")
        response_dict: dict[str, Any] | None

        with self.metrics_client.timeit(
            f"accuweather.request.{request_type}.get", sample_rate=self.metrics_sample_rate
        ):
            response: Response = await self.http_client.get(url_path, params=params)

            response.raise_for_status()

        if (response_dict := process_api_response(response.json())) is None:
            self.metrics_client.increment(f"accuweather.request.{request_type}.processor.error")
            return None

        if should_cache:
            cache_key = self.cache_key_for_accuweather_request(url_path, params)
            response_expiry: str = response.headers.get("Expires")
            try:
                cached_request_ttl = await self.store_request_into_cache(
                    cache_key, response_dict, response_expiry, cache_ttl_sec
                )
                # add the ttl of the just cached request to the response dict we return
                response_dict["cached_request_ttl"] = cached_request_ttl
            except (CacheAdapterError, ValueError) as exc:
                logger.error(f"Error with storing Accuweather to cache: {exc}")
                error_type = (
                    "set_error" if isinstance(exc, CacheAdapterError) else "ttl_date_error"
                )
                self.metrics_client.increment(f"accuweather.cache.store.{error_type}")
                raise AccuweatherError(AccuweatherErrorMessages.CACHE_WRITE_ERROR)

        return response_dict

    async def store_request_into_cache(
        self,
        cache_key: str,
        response_dict: dict[str, Any],
        response_expiry: str,
        cache_ttl_sec: int,
    ) -> int:
        """Store the request into cache. Also ensures that the cache ttl is
        at least `cached_ttl_sec`. Returns the cached request's ttl in seconds.
        """
        with self.metrics_client.timeit(
            "accuweather.cache.store", sample_rate=self.metrics_sample_rate
        ):
            expiry_delta: datetime.timedelta = parser.parse(
                response_expiry
            ) - datetime.datetime.now(datetime.timezone.utc)
            cache_ttl: datetime.timedelta = max(
                expiry_delta, datetime.timedelta(seconds=cache_ttl_sec)
            )
            cache_value = orjson.dumps(response_dict)
            await self.cache.set(cache_key, cache_value, ttl=cache_ttl)

        return cache_ttl.seconds

    def emit_cache_fetch_metrics(
        self, cached_data: list[bytes | None], skip_location_key=False
    ) -> None:
        """Emit cache fetch metrics.

        Params:
            - `cached_data` {list[bytes]} A list of bytes for location_key,
              current_condition, forecast
            -  `skip_location_key` A boolean to determine whether location was looked up.
        """
        location, current, forecast = False, False, False
        match cached_data:
            case []:
                pass
            # the last variable is ttl but is omitted here since we don't need to use but need
            # it to satisfy this match case
            case [location_cached, current_cached, forecast_cached, _]:
                location, current, forecast = (
                    location_cached is not None,
                    current_cached is not None,
                    forecast_cached is not None,
                )
            case _:  # pragma: no cover
                pass

        if not skip_location_key:
            self.metrics_client.increment(
                "accuweather.cache.hit.locations"
                if location
                else "accuweather.cache.fetch.miss.locations",
                sample_rate=self.metrics_sample_rate,
            )

        self.metrics_client.increment(
            "accuweather.cache.hit.currentconditions"
            if current
            else "accuweather.cache.fetch.miss.currentconditions",
            sample_rate=self.metrics_sample_rate,
        )
        self.metrics_client.increment(
            "accuweather.cache.hit.forecasts"
            if forecast
            else "accuweather.cache.fetch.miss.forecasts",
            sample_rate=self.metrics_sample_rate,
        )

    def parse_cached_data(self, cached_data: list[bytes | None]) -> WeatherData:
        """Parse the weather data from cache.

        Upon parsing errors, it will return the successfully parsed data thus far.

        Params:
            - `cached_data` {list[bytes]} A list of bytes for location_key,
              current_conditions, forecast, ttl
        """
        if len(cached_data) == 0:
            return WeatherData()

        location_cached, current_cached, forecast_cached, hourly_forecast_cached, ttl_cached = (
            cached_data
        )

        location: AccuweatherLocation | None = None
        current_conditions: CurrentConditions | None = None
        forecast: Forecast | None = None
        hourly_forecasts: list[HourlyForecast] | None = None
        ttl: int | None = None

        try:
            if location_cached is not None:
                location = AccuweatherLocation.model_validate(orjson.loads(location_cached))
            if current_cached is not None:
                current_conditions = CurrentConditions.model_validate(orjson.loads(current_cached))
            if forecast_cached is not None:
                forecast = Forecast.model_validate(orjson.loads(forecast_cached))
            if hourly_forecast_cached is not None:
                # TODO @herraj validate model
                hourly_forecasts = orjson.loads(hourly_forecast_cached)["hourly_forecasts"]
            if ttl_cached is not None:
                # redis returns the TTL value as an integer, however, we are explicitly casting
                # the value returned from the cache since it's received as bytes as the method
                # argument. This satisfies the type checker.
                ttl = cast(int, ttl_cached)
        except ValidationError as exc:
            logger.error(f"Failed to load weather report data from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.data.error")
        return WeatherData(location, current_conditions, forecast, hourly_forecasts, ttl)

    def get_location_key_query_params(self, city: str) -> dict[str, str]:
        """Get the query parameters for the location key for a given city."""
        return {
            self.url_param_api_key: self.api_key,
            self.url_cities_param_query: city,
            ALIAS_PARAM: ALIAS_PARAM_VALUE,
        }

    async def get_weather_report(self, weather_context: WeatherContext) -> WeatherReport | None:
        """Get weather report either via location key or geolocation."""
        if weather_context.geolocation.key:
            return await self.get_weather_report_with_location_key(weather_context)

        return await self.get_weather_report_with_geolocation(weather_context)

    @staticmethod
    def get_localized_city_name(
        location: AccuweatherLocation, weather_context: WeatherContext
    ) -> str | None:
        """Get city name based on specified language."""
        geolocation = weather_context.geolocation
        language = get_language(weather_context.languages)
        normalized_lang = (
            "en" if language.startswith("en") else "es" if language.startswith("es") else language
        )

        # ensure city was not overridden, if so city_names do not contain what we need
        if location.localized_name == geolocation.city_names.get("en"):
            return geolocation.city_names.get(normalized_lang)

        return location.localized_name

    @staticmethod
    def get_region_for_weather_report(
        location: AccuweatherLocation, weather_context: WeatherContext
    ) -> str | None:
        """Get region based on request country origin and the country of the requested city."""
        geolocation = weather_context.geolocation
        # we don't override country_name so it should tell us where the request came from
        request_origin_country = geolocation.country_name
        requested_country = geolocation.country
        if request_origin_country in ["Canada", "United States"] and requested_country in [
            "CA",
            "US",
        ]:
            return location.administrative_area_id
        else:
            return location.country_name

    async def get_weather_report_with_location_key(
        self, weather_context: WeatherContext
    ) -> WeatherReport | None:
        """Get weather information from AccuWeather.

        Firstly, it will look up the Redis cache for the current condition,
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
        language = get_language(weather_context.languages)
        location_key = weather_context.geolocation.key
        # Look up for all the weather data from the cache.
        try:
            with self.metrics_client.timeit(
                "accuweather.cache.fetch-via-location-key", sample_rate=self.metrics_sample_rate
            ):
                cached_data: list[bytes | None] = await self.cache.run_script(
                    sid=SCRIPT_LOCATION_KEY_ID,
                    keys=[],
                    # The order matters below.
                    # See `LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION` for details.
                    args=[
                        self.cache_key_template(
                            WeatherDataType.CURRENT_CONDITIONS, language
                        ).format(location_key=location_key),
                        self.cache_key_template(WeatherDataType.FORECAST, language).format(
                            location_key=location_key
                        ),
                    ],
                    readonly=True,
                )
                if cached_data:
                    cached_data = [LOCATION_SENTINEL, *cached_data]
        except CacheAdapterError as exc:
            logger.error(f"Failed to fetch weather report from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.fetch-via-location-key.error")
            # Propagate the error for circuit breaking.
            raise AccuweatherError(
                AccuweatherErrorMessages.CACHE_READ_ERROR, exception=exc
            ) from exc

        self.emit_cache_fetch_metrics(cached_data, skip_location_key=True)
        cached_report = self.parse_cached_data(cached_data)
        return await self.make_weather_report(cached_report, weather_context)

    async def _fetch_from_cache(
        self,
        weather_context: WeatherContext,
    ) -> list[bytes | None] | None:
        """Fetch weather data from cache."""
        geolocation = weather_context.geolocation
        country = geolocation.country
        city = weather_context.selected_city
        language = get_language(weather_context.languages)
        region = weather_context.selected_region

        if country is None or city is None:
            return None

        cache_key: str
        if region is not None:
            cache_key = self.cache_key_for_accuweather_request(
                self.url_cities_admin_path.format(country_code=country, admin_code=region),
                query_params=self.get_location_key_query_params(city),
            )
        else:
            cache_key = self.cache_key_for_accuweather_request(
                self.url_cities_path.format(country_code=country),
                query_params=self.get_location_key_query_params(city),
            )

        with self.metrics_client.timeit(
            "accuweather.cache.fetch", sample_rate=self.metrics_sample_rate
        ):
            cached_data: list = await self.cache.run_script(
                sid=SCRIPT_ID_BULK_FETCH_VIA_GEOLOCATION,
                keys=[cache_key],
                # The order matters below. See `LUA_SCRIPT_CACHE_BULK_FETCH` for details.
                args=[
                    self.cache_key_template(WeatherDataType.CURRENT_CONDITIONS, language),
                    self.cache_key_template(WeatherDataType.FORECAST, language),
                    self.cache_key_template(WeatherDataType.HOURLY_FORECAST, language),
                    self.url_location_key_placeholder,
                ],
                readonly=True,
            )
            return cached_data if cached_data else None

    async def get_weather_report_with_geolocation(
        self, weather_context: WeatherContext
    ) -> WeatherReport | None:
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
        geolocation: Location = weather_context.geolocation
        country: str | None = geolocation.country
        city: str | None = geolocation.city

        if country is None or city is None:
            self.metrics_client.increment(
                "accuweather.request.location.not_provided", sample_rate=self.metrics_sample_rate
            )
            raise MissingLocationKeyError(geolocation)

        try:
            cached_data, is_skipped = await pathfinder.explore(
                weather_context, self._fetch_from_cache
            )
        except CacheAdapterError as exc:
            logger.error(f"Failed to fetch weather report from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.fetch.error")
            # Propagate the error for circuit breaking.
            raise AccuweatherError(
                AccuweatherErrorMessages.CACHE_READ_ERROR, exception=exc
            ) from exc

        if is_skipped:
            raise MissingLocationKeyError(geolocation)

        cached_data = cached_data if cached_data is not None else []
        self.emit_cache_fetch_metrics(cached_data)
        cached_report = self.parse_cached_data(cached_data)

        return await self.make_weather_report(cached_report, weather_context)

    async def make_weather_report(
        self, cached_report: WeatherData, weather_context: WeatherContext
    ) -> WeatherReport | None:
        """Make a `WeatherReport` either using the cached data or fetching from AccuWeather.

        Raises:
            AccuWeatherError: Failed request or 4xx and 5xx response from AccuWeather.
        """
        geolocation = weather_context.geolocation
        location_key = geolocation.key
        language = get_language(weather_context.languages)
        request_source = weather_context.request_source

        async def as_awaitable(val: Any) -> Any:
            """Wrap a non-awaitable value into a coroutine and resolve it right away."""
            return val

        location, current_conditions, forecast, hourly_forecast, ttl = cached_report

        if location_key and location is None:
            # request was made with location key rather than geolocation
            # so location info is not in the cache
            location = AccuweatherLocation(
                localized_name="N/A",
                key=location_key,
                administrative_area_id="N/A",
                country_name="N/A",
            )
        # if all the other three values are present, ttl here would be a valid ttl value
        if location and current_conditions and forecast and hourly_forecast and ttl:
            # Return the weather report with the values returned from the cache.
            city_name = self.get_localized_city_name(location, weather_context)
            admin_area = self.get_region_for_weather_report(location, weather_context)
            if request_source == URLBAR_REQUEST_SOURCE:
                current_conditions, forecast = update_weather_url_with_suggest_partner_code(
                    current_conditions, forecast
                )

            # TODO @herraj make hourly_forecast required?
            return WeatherReport(
                city_name=city_name if city_name else location.localized_name,
                region_code=admin_area,
                current_conditions=current_conditions,
                forecast=forecast,
                hourly_forecasts=hourly_forecast,
                ttl=ttl,
            )
        # The cached report is incomplete, now fetching from AccuWeather.
        if location is None:
            try:
                location, _ = await pathfinder.explore(
                    weather_context, self.get_location_by_geolocation
                )
            except AccuweatherError as exc:
                logger.warning(f"{exc}")
                return None

            if location is None:
                raise MissingLocationKeyError(geolocation)

        try:
            async with asyncio.TaskGroup() as tg:
                task_current = tg.create_task(
                    self.get_current_conditions(location.key, language)
                    if current_conditions is None
                    else as_awaitable(
                        CurrentConditionsWithTTL(
                            current_conditions=current_conditions,
                            ttl=self.cached_current_condition_ttl_sec,
                        )
                    )
                )
                task_forecast = tg.create_task(
                    self.get_forecast(location.key, language)
                    if forecast is None
                    else as_awaitable(
                        ForecastWithTTL(forecast=forecast, ttl=self.cached_forecast_ttl_sec)
                    )
                )
                task_hourly_forecast = tg.create_task(
                    self.get_hourly_forecast(location.key, language)
                    if hourly_forecast is None
                    else as_awaitable(
                        HourlyForecastWithTTL(
                            hourly_forecast=hourly_forecast, ttl=self.cached_forecast_ttl_sec
                        )
                    )
                )

        except ExceptionGroup as e:
            raise AccuweatherError(
                AccuweatherErrorMessages.FAILED_WEATHER_REPORT, exceptions=e.exceptions
            )

        if (
            (current_conditions_response := await task_current) is not None
            and (forecast_response := await task_forecast)
            and (hourly_forecast_response := await task_hourly_forecast)
        ):
            current_conditions, current_conditions_ttl = current_conditions_response
            forecast, forecast_ttl = forecast_response
            # TODO @herraj not pulling ttl out
            hourly_forecast, _ = hourly_forecast_response
            weather_report_ttl = min(current_conditions_ttl, forecast_ttl)
            city_name = self.get_localized_city_name(location, weather_context)
            admin_area = self.get_region_for_weather_report(location, weather_context)
            if request_source == URLBAR_REQUEST_SOURCE and current_conditions and forecast:
                current_conditions, forecast = update_weather_url_with_suggest_partner_code(
                    current_conditions, forecast
                )

            return (
                WeatherReport(
                    city_name=city_name if city_name else location.localized_name,
                    region_code=admin_area,
                    current_conditions=current_conditions,
                    forecast=forecast,
                    hourly_forecasts=hourly_forecast,
                    ttl=weather_report_ttl,
                )
                if current_conditions is not None and forecast is not None
                else None
            )
        else:
            return None

    async def get_location_by_geolocation(
        self, weather_context: WeatherContext
    ) -> AccuweatherLocation | None:
        """Return location data for a specific country and city or None if
        location data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-locations-api/apis/get/locations/v1/cities/{countryCode}/{adminCode}/search
        """
        geolocation = weather_context.geolocation
        country = geolocation.country
        city = weather_context.selected_city
        region = weather_context.selected_region

        if country is None or city is None:
            return None

        if region:
            url_path = self.url_cities_admin_path.format(country_code=country, admin_code=region)
        else:
            url_path = self.url_cities_path.format(country_code=country)

        try:
            response: dict[str, Any] | None = await self.request_upstream(
                url_path,
                params=self.get_location_key_query_params(city),
                request_type=RequestType.LOCATIONS,
                process_api_response=process_location_response,
                cache_ttl_sec=self.cached_location_key_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError(
                AccuweatherErrorMessages.HTTP_UNEXPECTED_LOCATION_RESPONSE,
                url_path=url_path,
                city=city,
            ) from error
        except Exception as exc:
            raise AccuweatherError(
                AccuweatherErrorMessages.UNEXPECTED_GEOLOCATION_ERROR,
                exception_class_name=exc.__class__.__name__,
            ) from exc

        if country and city:
            if response:
                # record the region that gave a location
                set_region_mapping(country, city, region)
            else:
                # record the country, region, city that did not provide a location
                increment_skip_cities_mapping(country, region, city)

        return AccuweatherLocation(**response) if response else None

    async def get_current_conditions(
        self, location_key: str, language: str
    ) -> CurrentConditionsWithTTL | None:
        """Return current conditions data for a specific location or None if current
        conditions data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-current-conditions-api/apis/get/currentconditions/v1/{locationKey}
        """
        try:
            response: dict[str, Any] | None = await self.request_upstream(
                self.url_current_conditions_path.format(location_key=location_key),
                params={self.url_param_api_key: self.api_key, LANGUAGE_PARAM: language},
                request_type=RequestType.CURRENT_CONDITIONS,
                process_api_response=process_current_condition_response,
                cache_ttl_sec=self.cached_current_condition_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError(
                AccuweatherErrorMessages.HTTP_UNEXPECTED_CURRENT_CONDITIONS_RESPONSE,
                current_conditions_url=self.url_current_conditions_path.format(
                    location_key=location_key
                ),
            ) from error
        except Exception as exc:
            raise AccuweatherError(
                AccuweatherErrorMessages.UNEXPECTED_CURRENT_CONDITIONS_ERROR,
                exception_class_name=exc.__class__.__name__,
            ) from exc

        return (
            CurrentConditionsWithTTL(
                current_conditions=CurrentConditions(
                    url=response["url"],
                    summary=response["summary"],
                    icon_id=response["icon_id"],
                    temperature=Temperature(**response["temperature"]),
                ),
                ttl=response["cached_request_ttl"],
            )
            if response
            else None
        )

    async def get_forecast(self, location_key: str, language: str) -> ForecastWithTTL | None:
        """Return daily forecast data for a specific location or None if daily
        forecast data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-forecast-api/apis/get/forecasts/v1/daily/1day/{locationKey}
        """
        try:
            response: dict[str, Any] | None = await self.request_upstream(
                self.url_forecasts_path.format(location_key=location_key),
                params={self.url_param_api_key: self.api_key, LANGUAGE_PARAM: language},
                request_type=RequestType.FORECASTS,
                process_api_response=process_forecast_response,
                cache_ttl_sec=self.cached_forecast_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError(
                AccuweatherErrorMessages.HTTP_UNEXPECTED_FORECAST_RESPONSE,
                forecast_url=self.url_forecasts_path.format(location_key=location_key),
            ) from error
        except Exception as exc:
            raise AccuweatherError(
                AccuweatherErrorMessages.UNEXPECTED_FORECAST_ERROR,
                exception_class_name=exc.__class__.__name__,
            ) from exc

        return (
            ForecastWithTTL(
                forecast=Forecast(
                    url=response["url"],
                    summary=response["summary"],
                    high=Temperature(**response["high"]),
                    low=Temperature(**response["low"]),
                ),
                ttl=response["cached_request_ttl"],
            )
            if response
            else None
        )

    async def get_hourly_forecast(
        self, location_key: str, language: str
    ) -> HourlyForecastWithTTL | None:
        """Return hourly forecast data for a specific location or None if hourly
        forecast data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://apidev.accuweather.com/developers/forecastsAPIguide#ForecastHourly12
        """
        try:
            response: dict[str, Any] | None = await self.request_upstream(
                self.url_hourly_forecasts_path.format(location_key=location_key),
                params={self.url_param_api_key: self.api_key, LANGUAGE_PARAM: language},
                request_type=RequestType.HOURLY_FORECASTS,
                process_api_response=process_hourly_forecast_response,
                cache_ttl_sec=self.cached_hourly_forecast_ttl_sec,
            )
            if response:
                # {"hourly_forecasts: [], cached_request_ttl: 123"}
                return HourlyForecastWithTTL(
                    hourly_forecast=response.get("hourly_forecasts", []),
                    ttl=response.get("cached_request_ttl", self.cached_hourly_forecast_ttl_sec),
                )
            else:
                return None
        except HTTPError as error:
            raise AccuweatherError(
                AccuweatherErrorMessages.HTTP_UNEXPECTED_HOURLY_FORCAST_ERROR,
                forecast_url=self.url_hourly_forecasts_path.format(location_key=location_key),
            ) from error
        except Exception as exc:
            raise AccuweatherError(
                AccuweatherErrorMessages.UNEXPECTED_HOURLY_FORCAST_ERROR,
                exception_class_name=exc.__class__.__name__,
            ) from exc

    async def get_location_completion(
        self, weather_context: WeatherContext, search_term: str
    ) -> list[LocationCompletion] | None:
        """Fetch a list of locations from the Accuweather API given a search term and location."""
        if not search_term:
            return None
        geolocation = weather_context.geolocation
        language = get_language(weather_context.languages)

        url_path = self.url_location_completion_path

        # if unable to derive country code from client geolocation, remove it from the url
        if not geolocation.country:
            url_path = url_path.replace("/{country_code}", "")
        else:
            url_path = url_path.format(country_code=geolocation.country)

        params = {
            "q": search_term,
            self.url_param_api_key: self.api_key,
            LOCATION_COMPLETE_ALIAS_PARAM: LOCATION_COMPLETE_ALIAS_PARAM_VALUE,
            LANGUAGE_PARAM: language,
        }

        try:
            response: dict[str, Any] | None = await self.request_upstream(
                url_path,
                params=params,
                request_type=RequestType.AUTOCOMPLETE,
                process_api_response=process_location_completion_response,
                should_cache=False,
            )
        except HTTPError as error:
            raise AccuweatherError(
                AccuweatherErrorMessages.HTTP_LOCATION_COMPLETION_ERROR,
                url_path=url_path,
                search_term=search_term,
                language=language,
            ) from error
        except Exception as exc:
            raise AccuweatherError(
                AccuweatherErrorMessages.UNEXPECTED_LOCATION_COMPLETION_ERROR,
                exception_class_name=exc.__class__.__name__,
            ) from exc

        return (
            [LocationCompletion(**cast(dict[str, Any], item)) for item in response]
            if response
            else None
        )

    async def shutdown(self) -> None:
        """Close out the cache during shutdown."""
        await self.http_client.aclose()
        await self.cache.close()
