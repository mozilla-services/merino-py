"""A wrapper for AccuWeather API interactions."""
import asyncio
from typing import Optional

from httpx import AsyncClient, HTTPError, Response
from pydantic import BaseModel

from merino.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherReport,
)


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
    url_base: str
    url_param_api_key: str
    url_postalcodes_path: str
    url_postalcodes_param_query: str
    url_current_conditions_path: str
    url_forecasts_path: str

    def __init__(
        self,
        api_key: str,
        url_base: str,
        url_param_api_key: str,
        url_postalcodes_path: str,
        url_postalcodes_param_query: str,
        url_current_conditions_path: str,
        url_forecasts_path: str,
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
        self.url_base = url_base
        self.url_param_api_key = url_param_api_key
        self.url_postalcodes_path = url_postalcodes_path
        self.url_postalcodes_param_query = url_postalcodes_param_query
        self.url_current_conditions_path = url_current_conditions_path
        self.url_forecasts_path = url_forecasts_path

    def cache_inputs_for_weather_report(self, geolocation: Location) -> Optional[bytes]:
        """Return the inputs used to form the cache key for looking up and storing the current
        conditions and forecast for a location.
        """
        if geolocation.country is None or geolocation.postal_code is None:
            return None

        return (geolocation.country + geolocation.postal_code).encode("utf-8")

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
            response: Response = await client.get(
                self.url_postalcodes_path.format(country_code=country),
                params={
                    self.url_param_api_key: self.api_key,
                    self.url_postalcodes_param_query: postal_code,
                },
            )
            response.raise_for_status()
        except HTTPError as error:
            raise AccuweatherError("Unexpected location response") from error

        match response.json():
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
            response: Response = await client.get(
                self.url_current_conditions_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
            )
            response.raise_for_status()
        except HTTPError as error:
            raise AccuweatherError("Unexpected current conditions response") from error

        match response.json():
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
                # line as unreachable. See
                # https://github.com/python/mypy/issues/12770
                return CurrentConditions(  # type: ignore
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
            response: Response = await client.get(
                self.url_forecasts_path.format(location_key=location_key),
                params={
                    self.url_param_api_key: self.api_key,
                },
            )
            response.raise_for_status()
        except HTTPError as error:
            raise AccuweatherError("Unexpected forecast response") from error

        match response.json():
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
                # line as unreachable. See
                # https://github.com/python/mypy/issues/12770
                return Forecast(  # type: ignore
                    url=url,
                    summary=summary,
                    high=Temperature(**{high_unit.lower(): high_value}),
                    low=Temperature(**{low_unit.lower(): low_value}),
                )
            case _:
                return None
