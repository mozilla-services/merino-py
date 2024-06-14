"""A wrapper for AccuWeather API interactions."""

import asyncio
import datetime
import functools
import hashlib
import json
import logging
from enum import Enum
from typing import Any, Callable, NamedTuple, cast

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
    LocationCompletion,
    Temperature,
    WeatherReport,
)

logger = logging.getLogger(__name__)

PARTNER_PARAM_ID: str | None = settings.accuweather.get("url_param_partner_code")
PARTNER_CODE: str | None = settings.accuweather.get("partner_code")

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
#     conditions and forecast for that key in the cache. It returns a 3-element array
#     `[location_key, current_condition, forecast]`. The last two element can be `nil`
#     if they are not present in the cache
#   - If the location key is missing, it will return an empty array
#   - If the forecast and current_conditions TTLs are a non-positive value (-1 or -2),
#     it will return ttl as false, which is translated to None type in app code.
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

    local current_conditions_ttl = redis.call("TTL", condition_key)
    local forecast_ttl = redis.call("TTL", forecast_key)
    local ttl = false

    if current_conditions_ttl >= 0 and forecast_ttl >= 0 then
        ttl = math.min(current_conditions_ttl, forecast_ttl)
    end
    return {location_key, current_conditions, forecast, ttl}
"""
SCRIPT_ID: str = "bulk_fetch"


# The Lua script to fetch the location key, current condition, forecast, and a TTL for
# a given a city-based_location key.
#
# Note:
#   - The script retrieves the cached current conditions and forecase data
#   - The cache key for current conditions and forecast should be provided
#     through `ARGV[1]` and `ARGV[2]`
#   - It returns a 3-element array (for compatability reasons the first value is nil.)
#     `[nil, current_condition, forecast]`. The last two element can be `nil`
#     if they are not present in the cache
#   - If the forecast and current_conditions TTLs are a non-positive value (-1 or -2),
#     it will return ttl as false, which is translated to None type in app code.
LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION: str = """
    local condition_key = ARGV[1]
    local forecast_key = ARGV[2]

    local current_conditions = redis.call("GET", condition_key)
    local forecast = redis.call("GET", forecast_key)

    local current_conditions_ttl = redis.call("TTL", condition_key)
    local forecast_ttl = redis.call("TTL", forecast_key)
    local ttl = false

    if current_conditions_ttl >= 0 and forecast_ttl >= 0 then
        ttl = math.min(current_conditions_ttl, forecast_ttl)
    end
    local location = nil
    return {location, current_conditions, forecast, ttl}
"""
SCRIPT_LOCATION_KEY_ID = "bulk_fetch_by_location_key"
LOCATION_COMPLETION_REQUEST_TYPE: str = "autocomplete"

ALIAS_PARAM: str = "alias"
ALIAS_PARAM_VALUE: str = "always"
LOCATION_COMPLETE_ALIAS_PARAM: str = "includealiases"
LOCATION_COMPLETE_ALIAS_PARAM_VALUE: str = "true"


class AccuweatherLocation(BaseModel):
    """Location model for response data from AccuWeather endpoints."""

    # Location key.
    key: str

    # Display name in local dialect set with language code in URL.
    # Default is US English (en-us).
    localized_name: str


class WeatherData(NamedTuple):
    """The quartet for weather data used internally."""

    location: AccuweatherLocation | None = None
    current_conditions: CurrentConditions | None = None
    forecast: Forecast | None = None
    ttl: int | None = None


class CurrentConditionsWithTTL(NamedTuple):
    """CurrentConditions and its TTL value that is used to build a WeatherReport instance"""

    current_conditions: CurrentConditions
    ttl: int


class ForecastWithTTL(NamedTuple):
    """Forecast and its TTL value that is used to build a WeatherReport instance"""

    forecast: Forecast
    ttl: int


class AccuweatherError(BackendError):
    """Error during interaction with the AccuWeather API."""


class WeatherDataType(Enum):
    """Enum to capture all types for weather data."""

    CURRENT_CONDITIONS = 1
    FORECAST = 2


class AccuweatherBackend:
    """Backend that connects to the AccuWeather API using City to find location key."""

    api_key: str
    cache: CacheAdapter
    cached_location_key_ttl_sec: int
    cached_current_condition_ttl_sec: int
    cached_forecast_ttl_sec: int
    metrics_client: aiodogstatsd.Client
    url_param_api_key: str
    url_cities_path: str
    url_cities_param_query: str
    url_current_conditions_path: str
    url_forecasts_path: str
    url_location_path: str
    url_location_key_placeholder: str
    url_location_completion_path: str
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
        url_cities_path: str,
        url_cities_param_query: str,
        url_current_conditions_path: str,
        url_forecasts_path: str,
        url_location_completion_path: str,
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
            or not url_cities_path
            or not url_cities_param_query
            or not url_current_conditions_path
            or not url_forecasts_path
            or not url_location_key_placeholder
        ):
            raise ValueError("One or more AccuWeather API URL parameters are undefined")

        self.api_key = api_key
        self.cache = cache
        # This registration is lazy (i.e. no interaction with Redis) and infallible.
        self.cache.register_script(
            SCRIPT_LOCATION_KEY_ID, LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION
        )
        self.cache.register_script(SCRIPT_ID, LUA_SCRIPT_CACHE_BULK_FETCH)
        self.cached_location_key_ttl_sec = cached_location_key_ttl_sec
        self.cached_current_condition_ttl_sec = cached_current_condition_ttl_sec
        self.cached_forecast_ttl_sec = cached_forecast_ttl_sec
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.url_param_api_key = url_param_api_key
        self.url_cities_path = url_cities_path
        self.url_cities_param_query = url_cities_param_query
        self.url_current_conditions_path = url_current_conditions_path
        self.url_forecasts_path = url_forecasts_path
        self.url_location_completion_path = url_location_completion_path
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

            return f"{self.__class__.__name__}:v4:{url}:{extra_identifiers}"

        return f"{self.__class__.__name__}:v4:{url}"

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
        response_dict: dict[str, Any] | None

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
    ) -> int:
        """Store the request into cache. Also ensures that the cache ttl is
        at least `cached_ttl_sec`. Returns the cached request's ttl in seconds.
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
              current_conditions, forecast, ttl
        """
        if len(cached_data) == 0:
            return WeatherData()

        location_cached, current_cached, forecast_cached, ttl_cached = cached_data

        location: AccuweatherLocation | None = None
        current_conditions: CurrentConditions | None = None
        forecast: Forecast | None = None
        ttl: int | None = None

        try:
            if location_cached is not None:
                location = AccuweatherLocation.model_validate_json(location_cached)
            if current_cached is not None:
                current_conditions = CurrentConditions.model_validate_json(
                    current_cached
                )
            if forecast_cached is not None:
                forecast = Forecast.model_validate_json(forecast_cached)
            if ttl_cached is not None:
                # redis returns the TTL value as an integer, however, we are explicitly casting
                # the value returned from the cache since it's received as bytes as the method
                # argument. This satisfies the type checker.
                ttl = cast(int, ttl_cached)
        except ValidationError as exc:
            logger.error(f"Failed to load weather report data from Redis: {exc}")
            self.metrics_client.increment("accuweather.cache.data.error")

        return WeatherData(location, current_conditions, forecast, ttl)

    def get_location_key_query_params(self, city: str) -> dict[str, str]:
        """Get the query parameters for the location key for a given city."""
        return {
            self.url_param_api_key: self.api_key,
            self.url_cities_param_query: city,
            ALIAS_PARAM: ALIAS_PARAM_VALUE,
        }

    async def get_weather_report(
        self, geolocation: Location, location_key: str | None = None
    ) -> WeatherReport | None:
        """Get weather report either via location key or geolocation."""
        if location_key:
            return await self.get_weather_report_with_location_key(location_key)

        return await self.get_weather_report_with_geolocation(geolocation)

    async def get_weather_report_with_location_key(
        self, location_key
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
        # Look up for all the weather data from the cache.
        try:
            with self.metrics_client.timeit("accuweather.cache.fetch-via-location-key"):
                cached_data: list[bytes | None] = await self.cache.run_script(
                    sid=SCRIPT_LOCATION_KEY_ID,
                    keys=[],
                    # The order matters below.
                    # See `LUA_SCRIPT_CACHE_BULK_FETCH_VIA_LOCATION` for details.
                    args=[
                        self.cache_key_template(
                            WeatherDataType.CURRENT_CONDITIONS
                        ).format(location_key=location_key),
                        self.cache_key_template(WeatherDataType.FORECAST).format(
                            location_key=location_key
                        ),
                    ],
                )
        except CacheAdapterError as exc:
            logger.error(f"Failed to fetch weather report from Redis: {exc}")
            self.metrics_client.increment(
                "accuweather.cache.fetch-via-location-key.error"
            )
            return None

        self.emit_cache_fetch_metrics(cached_data, skip_location_key=True)
        cached_report = self.parse_cached_data(cached_data)
        location = Location(key=location_key)
        return await self.make_weather_report(cached_report, location)

    async def get_weather_report_with_geolocation(
        self, geolocation: Location
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
        country: str | None = geolocation.country
        region: str | None = geolocation.region
        city: str | None = geolocation.city
        if not country or not region or not city:
            raise AccuweatherError("Country and/or region/city unknown")

        cache_key: str = self.cache_key_for_accuweather_request(
            self.url_cities_path.format(country_code=country, admin_code=region),
            query_params=self.get_location_key_query_params(city),
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
        geolocation = Location(country=country, city=city, region=region)
        return await self.make_weather_report(cached_report, geolocation)

    async def make_weather_report(
        self, cached_report: WeatherData, geolocation: Location
    ) -> WeatherReport | None:
        """Make a `WeatherReport` either using the cached data or fetching from AccuWeather.

        Raises:
            AccuWeatherError: Failed request or 4xx and 5xx response from AccuWeather.
        """
        country = geolocation.country
        city = geolocation.city
        region = geolocation.region
        location_key = geolocation.key

        async def as_awaitable(val: Any) -> Any:
            """Wrap a non-awaitable value into a coroutine and resolve it right away."""
            return val

        location, current_conditions, forecast, ttl = cached_report

        if location_key and location is None:
            # request was made with location key rather than geolocation
            # so location info is not in the cache
            location = AccuweatherLocation(localized_name="N/A", key=location_key)

        # if all the other three values are present, ttl here would be a valid ttl value
        if location and current_conditions and forecast and ttl:
            # Return the weather report with the values returned from the cache.
            return WeatherReport(
                city_name=location.localized_name,
                current_conditions=current_conditions,
                forecast=forecast,
                ttl=ttl,
            )

        # The cached report is incomplete, now fetching from AccuWeather.
        if location is None:
            if country and city and region:
                if (
                    location := await self.get_location_by_geolocation(
                        country, city, region
                    )
                ) is None:
                    return None
            else:
                return None

        try:
            async with asyncio.TaskGroup() as tg:
                task_current = tg.create_task(
                    self.get_current_conditions(location.key)
                    if current_conditions is None
                    else as_awaitable(
                        CurrentConditionsWithTTL(
                            current_conditions=current_conditions,
                            ttl=self.cached_current_condition_ttl_sec,
                        )
                    )
                )
                task_forecast = tg.create_task(
                    self.get_forecast(location.key)
                    if forecast is None
                    else as_awaitable(
                        ForecastWithTTL(
                            forecast=forecast, ttl=self.cached_forecast_ttl_sec
                        )
                    )
                )
        except ExceptionGroup as e:
            raise AccuweatherError(f"Failed to fetch weather report: {e.exceptions}")

        if (current_conditions_response := await task_current) is not None and (
            forecast_response := await task_forecast
        ):
            current_conditions, current_conditions_ttl = current_conditions_response
            forecast, forecast_ttl = forecast_response
            weather_report_ttl = min(current_conditions_ttl, forecast_ttl)

            return (
                WeatherReport(
                    city_name=location.localized_name,
                    current_conditions=current_conditions,
                    forecast=forecast,
                    ttl=weather_report_ttl,
                )
                if current_conditions is not None and forecast is not None
                else None
            )
        else:
            return None

    async def get_location_by_geolocation(
        self, country: str, city: str, region: str
    ) -> AccuweatherLocation | None:
        """Return location data for a specific country and city or None if
        location data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-locations-api/apis/get/locations/v1/cities/{countryCode}/{adminCode}/search
        """
        try:
            response: dict[str, Any] | None = await self.get_request(
                self.url_cities_path.format(country_code=country, admin_code=region),
                params=self.get_location_key_query_params(city),
                process_api_response=process_location_response,
                cache_ttl_sec=self.cached_location_key_ttl_sec,
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected location response") from error

        return AccuweatherLocation(**response) if response else None

    async def get_current_conditions(
        self, location_key: str
    ) -> CurrentConditionsWithTTL | None:
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

    async def get_forecast(self, location_key: str) -> ForecastWithTTL | None:
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

    async def get_location_completion(
        self, geolocation: Location, search_term: str
    ) -> list[LocationCompletion] | None:
        """Fetch a list of locations from the Accuweather API given a search term and location."""
        if not search_term:
            return None

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
        }

        with self.metrics_client.timeit(
            f"accuweather.request." f"{LOCATION_COMPLETION_REQUEST_TYPE}.get"
        ):
            response: Response = await self.http_client.get(url_path, params=params)
            response.raise_for_status()

        processed_location_completions = process_location_completion_response(
            response.json()
        )

        location_completions = [
            LocationCompletion(**item) for item in processed_location_completions
        ]

        return location_completions

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


def process_location_completion_response(response: Any) -> list[dict[str, Any]]:
    """Process the API response for location completion request."""
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
            *_,
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
