"""A wrapper for AccuWeather API interactions."""
import asyncio
import datetime
import hashlib
import json
import logging
from json import JSONDecodeError
from typing import Any, Optional

import aiodogstatsd
from dateutil import parser
from httpx import URL, AsyncClient, HTTPError, InvalidURL, Response
from pydantic import BaseModel
from pydantic.datetime_parse import timedelta

from merino.cache.protocol import CacheAdapter
from merino.exceptions import (
    BackendError,
    CacheAdapterError,
    CacheEntryError,
    CacheMissError,
)
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)

logger = logging.getLogger(__name__)


class AccuweatherLocation(BaseModel):
    """Location model for response data from AccuWeather endpoints."""

    # Location key.
    key: str

    # Display name in local dialect set with language code in URL.
    # Default is US English (en-us).
    localized_name: str


class AccuweatherError(BackendError):
    """Error during interaction with the AccuWeather API."""


class AccuweatherBackend:
    """Backend that connects to the AccuWeather API."""

    api_key: str
    cache: CacheAdapter
    cached_report_ttl_sec: int
    metrics_client: aiodogstatsd.Client
    url_base: str
    url_param_api_key: str
    url_postalcodes_path: str
    url_postalcodes_param_query: str
    url_current_conditions_path: str
    url_forecasts_path: str
    url_param_partner_code: Optional[str]
    partner_code: Optional[str]

    def __init__(
        self,
        api_key: str,
        cache: CacheAdapter,
        cached_report_ttl_sec: int,
        metrics_client: aiodogstatsd.Client,
        url_base: str,
        url_param_api_key: str,
        url_postalcodes_path: str,
        url_postalcodes_param_query: str,
        url_current_conditions_path: str,
        url_forecasts_path: str,
        url_param_partner_code: Optional[str] = None,
        partner_code: Optional[str] = None,
    ) -> None:
        """Initialize the AccuWeather backend.

        Raises:
            ValueError: If API key or URL parameters are None or empty.
        """
        if not api_key:
            raise ValueError("AccuWeather API key not specified")

        if (
            not url_base
            or not url_param_api_key
            or not url_postalcodes_path
            or not url_postalcodes_param_query
            or not url_current_conditions_path
            or not url_forecasts_path
        ):
            raise ValueError("One or more AccuWeather API URL parameters are undefined")

        self.api_key = api_key
        self.cache = cache
        self.cached_report_ttl_sec = cached_report_ttl_sec
        self.metrics_client = metrics_client
        self.url_base = url_base
        self.url_param_api_key = url_param_api_key
        self.url_postalcodes_path = url_postalcodes_path
        self.url_postalcodes_param_query = url_postalcodes_param_query
        self.url_current_conditions_path = url_current_conditions_path
        self.url_forecasts_path = url_forecasts_path
        self.url_param_partner_code = url_param_partner_code
        self.partner_code = partner_code

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

            return f"{self.__class__.__name__}:v1:{url}:{extra_identifiers}"

        return f"{self.__class__.__name__}:v1:{url}"

    async def get_request(
        self, client: AsyncClient, url_path: str, params: dict[str, str] = {}
    ) -> dict[str, Any]:
        """Get API response. Attempt to get it from cache first,
        then actually make the call if there's a cache miss.
        """
        cache_key = self.cache_key_for_accuweather_request(url_path, params)
        response_dict: dict[str, str]

        # The top level path in the URL gives us a good enough idea of what type of request
        # we are calling from here.
        request_type: str = url_path.strip("/").split("/", 1)[0]
        try:
            response_dict = await self.fetch_request_from_cache(cache_key)
            self.metrics_client.increment(f"accuweather.cache.hit.{request_type}")
        except (CacheMissError, CacheEntryError, CacheAdapterError) as exc:
            error_type = "miss" if isinstance(exc, CacheMissError) else "error"
            self.metrics_client.increment(
                f"accuweather.cache.fetch.{error_type}.{request_type}"
            )

            with self.metrics_client.timeit(f"accuweather.request.{request_type}.get"):
                response: Response = await client.get(url_path, params=params)
                response.raise_for_status()

            response_expiry: str = response.headers.get("Expires")
            response_dict = response.json()

            try:
                await self.store_request_into_cache(
                    cache_key, response_dict, response_expiry
                )
            except (CacheAdapterError, ValueError) as exc:
                logger.error(f"Error with storing Accuweather to cache: {exc}")
                error_type = (
                    "set_error"
                    if isinstance(exc, CacheAdapterError)
                    else "ttl_date_error"
                )
                self.metrics_client.increment(f"accuweather.cache.store.{error_type}")
                raise AccuweatherError(
                    "Something went wrong with storing to cache. Did not update cache."
                )

        return response_dict

    async def store_request_into_cache(
        self, cache_key: str, response_dict: dict[str, Any], response_expiry: str
    ):
        """Store the request into cache. Also ensures that the cache ttl is
        at least `cached_report_ttl_sec`.
        """
        with self.metrics_client.timeit("accuweather.cache.store"):
            expiry_delta: timedelta = parser.parse(
                response_expiry
            ) - datetime.datetime.now(datetime.timezone.utc)
            cache_ttl: timedelta = max(
                expiry_delta, timedelta(seconds=self.cached_report_ttl_sec)
            )
            cache_value = json.dumps(response_dict).encode("utf-8")
            await self.cache.set(cache_key, cache_value, ttl=cache_ttl)

    async def fetch_request_from_cache(self, cache_key: str) -> dict[str, Any]:
        """Get the request from the cache."""
        with self.metrics_client.timeit("accuweather.cache.fetch"):
            response: Optional[bytes] = await self.cache.get(cache_key)
            if not response:
                raise CacheMissError

            try:
                response_dict: dict[str, Any] = json.loads(response)
                return response_dict
            except JSONDecodeError as e:
                raise CacheEntryError("Failed to parse cache entry") from e

    async def get_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:
        """Get weather information from AccuWeather.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        """
        country: Optional[str] = geolocation.country
        postal_code: Optional[str] = geolocation.postal_code
        if not country or not postal_code:
            raise AccuweatherError("Country and/or postal code unknown")

        async with AsyncClient(base_url=self.url_base) as client:
            if not (location := await self.get_location(client, country, postal_code)):
                return None
            try:
                async with asyncio.TaskGroup() as tg:
                    task_current = tg.create_task(
                        self.get_current_conditions(client, location.key)
                    )
                    task_forecast = tg.create_task(
                        self.get_forecast(client, location.key)
                    )
            except ExceptionGroup as e:
                raise AccuweatherError(
                    f"Failed to fetch weather report: {e.exceptions}"
                )

            return (
                WeatherReport(
                    city_name=location.localized_name,
                    current_conditions=current,
                    forecast=forecast,
                )
                if (current := await task_current) and (forecast := await task_forecast)
                else None
            )

    async def get_location(
        self, client: AsyncClient, country: str, postal_code: str
    ) -> Optional[AccuweatherLocation]:
        """Return location data for a specific country and postal code or None if
        location data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-locations-api/apis/get/locations/v1/postalcodes/{countryCode}/search
        """
        try:
            response_json: dict[str, str] = await self.get_request(
                client,
                self.url_postalcodes_path.format(country_code=country),
                params={
                    self.url_param_api_key: self.api_key,
                    self.url_postalcodes_param_query: postal_code,
                },
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected location response") from error

        match response_json:
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
                return AccuweatherLocation(key=key, localized_name=localized_name)  # type: ignore
            case _:
                return None

    async def get_current_conditions(
        self, client: AsyncClient, location_key: str
    ) -> Optional[CurrentConditions]:
        """Return current conditions data for a specific location or None if current
        conditions data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-current-conditions-api/apis/get/currentconditions/v1/{locationKey}
        """
        try:
            response_json: dict[str, str] = await self.get_request(
                client,
                self.url_current_conditions_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected current conditions response") from error

        match response_json:
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
                try:  # type: ignore
                    url = self._add_partner_code(url)
                except InvalidURL as error:  # pragma: no cover
                    raise AccuweatherError(
                        "Invalid URL in current conditions response"
                    ) from error

                return CurrentConditions(
                    url=url,
                    summary=summary,
                    icon_id=icon_id,
                    temperature=Temperature(c=c, f=f),
                )
            case _:
                return None

    async def get_forecast(
        self, client: AsyncClient, location_key: str
    ) -> Optional[Forecast]:
        """Return daily forecast data for a specific location or None if daily
        forecast data is not found.

        Raises:
            AccuweatherError: Failed request or 4xx and 5xx response from AccuWeather.
        Reference:
            https://developer.accuweather.com/accuweather-forecast-api/apis/get/forecasts/v1/daily/1day/{locationKey}
        """
        try:
            response_json: dict[str, Any] = await self.get_request(
                client,
                self.url_forecasts_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
            )
        except HTTPError as error:
            raise AccuweatherError("Unexpected forecast response") from error

        match response_json:
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
                try:  # type: ignore
                    url = self._add_partner_code(url)
                except InvalidURL as error:  # pragma: no cover
                    raise AccuweatherError(
                        "Invalid URL in forecast response"
                    ) from error

                return Forecast(
                    url=url,
                    summary=summary,
                    high=Temperature(**{high_unit.lower(): high_value}),
                    low=Temperature(**{low_unit.lower(): low_value}),
                )
            case _:
                return None

    def _add_partner_code(self, url: str) -> str:
        if not self.url_param_partner_code or not self.partner_code:
            return url

        parsed_url = URL(url)
        return str(
            parsed_url.copy_add_param(self.url_param_partner_code, self.partner_code)
        )

    async def shutdown(self) -> None:
        """Close out the cache during shutdown."""
        await self.cache.close()
