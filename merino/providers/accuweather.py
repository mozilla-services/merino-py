"""AccuWeather integration."""
import logging
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion, SuggestionRequest

API_KEY: str = settings.providers.accuweather.api_key
CLIENT_IP_OVERRIDE: str = settings.location.client_ip_override
SCORE: float = settings.providers.accuweather.score

# Endpoint URL components
URL_BASE: str = settings.providers.accuweather.url_base
URL_PARAM_API_KEY: str = settings.providers.accuweather.url_param_api_key
URL_CURRENT_CONDITIONS_PATH: str = (
    settings.providers.accuweather.url_current_conditions_path
)
URL_POSTALCODES_PATH: str = settings.providers.accuweather.url_postalcodes_path
URL_POSTALCODES_PARAM_QUERY: str = (
    settings.providers.accuweather.url_postalcodes_param_query
)
URL_FORECASTS_PATH: str = settings.providers.accuweather.url_forecasts_path

logger = logging.getLogger(__name__)


class Temperature(BaseModel):
    """Model for temperature with C and F values."""

    c: Optional[float] = None
    f: Optional[float] = None

    def __init__(self, c: Optional[float] = None, f: Optional[float] = None):
        super().__init__(c=c, f=f)
        if c is None and f is not None:
            self.c = round((f - 32) * 5 / 9, 1)
        if f is None and c is not None:
            self.f = round(c * 9 / 5 + 32)


class CurrentConditions(BaseModel):
    """Model for AccuWeather current conditions."""

    url: HttpUrl
    summary: str
    icon_id: int
    temperature: Temperature


class Forecast(BaseModel):
    """Model for AccuWeather one-day forecasts."""

    url: HttpUrl
    summary: str
    high: Temperature
    low: Temperature


class Suggestion(BaseSuggestion):
    """Model for AccuWeather suggestions."""

    city_name: str
    current_conditions: CurrentConditions
    forecast: Forecast


class Provider(BaseProvider):
    """Suggestion provider for AccuWeather."""

    # In normal usage this is None, but tests can create the provider with a
    # FastAPI instance to fetch mock responses from it. See `__init__()`.
    _app: Optional[FastAPI]

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        name: str = "accuweather",
        enabled_by_default: bool = False,
        **kwargs: Any,
    ) -> None:
        self._app = app
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide AccuWeather suggestions."""
        if API_KEY == "":
            logger.warning("AccuWeather API key not specified")
            return []

        location = srequest.geolocation
        country = location.country
        postal_code = location.postal_code
        if country is None or postal_code is None:
            logger.warning("Country and/or postal code unknown")
            return []

        async with httpx.AsyncClient(app=self._app, base_url=URL_BASE) as client:
            suggestions = await self._get_weather(
                client,
                country=country,
                postal_code=postal_code,
            )
            return suggestions

    async def _get_weather(
        self, client: httpx.AsyncClient, country: str, postal_code: str
    ) -> list[BaseSuggestion]:
        # Get the AccuWeather location key for the country and postal codes.
        try:
            location_resp = await client.get(
                URL_POSTALCODES_PATH.format(country_code=country),
                params={
                    URL_PARAM_API_KEY: API_KEY,
                    URL_POSTALCODES_PARAM_QUERY: postal_code,
                },
            )
            location = location_resp.json()[0]
            location_key = location["Key"]
        except Exception:
            return []

        # Get the current conditions for the location key.
        try:
            current_conditions_resp = await client.get(
                URL_CURRENT_CONDITIONS_PATH.format(location_key=location_key),
                params={
                    URL_PARAM_API_KEY: API_KEY,
                },
            )
            current_conditions_data = current_conditions_resp.json()[0]
        except Exception:
            return []

        current_conditions = self._parse_current_conditions(current_conditions_data)
        if current_conditions is None:
            logger.warning("Unexpected current conditions response")
            return []

        # Get the forecast for the location key.
        try:
            forecasts_resp = await client.get(
                URL_FORECASTS_PATH.format(location_key=location_key),
                params={
                    URL_PARAM_API_KEY: API_KEY,
                },
            )
            forecasts_data = forecasts_resp.json()
        except Exception:
            return []

        forecast = self._parse_forecast(forecasts_data)
        if forecast is None:
            logger.warning("Unexpected forecast response")
            return []

        city_name = location.get("LocalizedName")
        return [
            Suggestion(
                title=f"Weather for {city_name}",
                url=current_conditions.url,
                provider=self.name,
                is_sponsored=False,
                score=SCORE,
                icon=None,
                city_name=city_name,
                current_conditions=current_conditions,
                forecast=forecast,
            )
        ]

    def _parse_current_conditions(self, data: Any) -> Optional[CurrentConditions]:
        match data:
            case {
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
            }:
                return CurrentConditions(
                    url=url,
                    summary=summary,
                    icon_id=icon_id,
                    temperature=Temperature(c=c, f=f),
                )
            case _:
                return None

    def _parse_forecast(self, data: Any) -> Optional[Forecast]:
        match data:
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
                                "Unit": high_unit,
                            },
                            "Minimum": {
                                "Value": low_value,
                                "Unit": low_unit,
                            },
                        },
                    }
                ],
            }:
                # `type: ignore` is necessary because mypy gets confused when
                # matching structures of type `Any` and reports the following
                # line as unreachable. See
                # https://github.com/python/mypy/issues/12770
                high = self._parse_forecast_temperature(high_value, high_unit)  # type: ignore
                if high is None:
                    logger.warning("Unexpected forecast high")
                    return None

                low = self._parse_forecast_temperature(low_value, low_unit)
                if low is None:
                    logger.warning("Unexpected forecast low")
                    return None

                return Forecast(url=url, summary=summary, high=high, low=low)
            case _:
                return None

    def _parse_forecast_temperature(
        self, value: float, unit: str
    ) -> Optional[Temperature]:
        match unit:
            case "C" | "c":
                return Temperature(c=value)
            case "F" | "f":
                return Temperature(f=value)
            case _:
                return None
