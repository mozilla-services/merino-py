"""AccuWeather integration."""
import logging
from typing import Any, Optional

import httpx
from fastapi import FastAPI

from merino.config import settings
from merino.middleware.geolocation import ctxvar_geolocation
from merino.providers.base import BaseProvider, BaseSuggestion

API_KEY: str = settings.providers.accuweather.api_key
CLIENT_IP_OVERRIDE: str = settings.location.client_ip_override
SCORE: float = settings.providers.accuweather.score

# Endpoint URL components
URL_BASE: str = settings.providers.accuweather.url_base
URL_PARAM_API_KEY: str = settings.providers.accuweather.url_param_api_key
URL_POSTALCODES_PATH: str = settings.providers.accuweather.url_postalcodes_path
URL_POSTALCODES_PARAM_QUERY: str = (
    settings.providers.accuweather.url_postalcodes_param_query
)
URL_FORECASTS_PATH: str = settings.providers.accuweather.url_forecasts_path

logger = logging.getLogger(__name__)


class Suggestion(BaseSuggestion):
    """Model for AccuWeather suggestions."""

    city_name: Optional[str] = None
    temperature_unit: Optional[str] = None
    high: Optional[float] = None
    low: Optional[float] = None
    day_summary: Optional[str] = None
    day_precipitation: Optional[bool] = None
    night_summary: Optional[str] = None
    night_precipitation: Optional[bool] = None


class Provider(BaseProvider):
    """Suggestion provider for AccuWeather."""

    # In normal usage this is None, but tests can create the provider with a
    # FastAPI instance to fetch mock responses from it. See `__init__()`.
    _app: Optional[FastAPI]

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        enabled_by_default: bool = False,
        **kwargs: Any
    ) -> None:
        self._app = app
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def query(self, q: str) -> list[BaseSuggestion]:
        """Provide AccuWeather suggestions."""
        if API_KEY == "":
            logger.warning("AccuWeather API key not specified")
            return []

        location = ctxvar_geolocation.get()
        country = location.country
        postal_code = location.postal_code
        if country is None or postal_code is None:
            logger.warning("Country and/or postal code unknown")
            return []

        async with httpx.AsyncClient(app=self._app, base_url=URL_BASE) as client:
            suggestions = await self._get_forecast(
                client,
                country=country,
                postal_code=postal_code,
            )
            return suggestions

    async def _get_forecast(
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

        # Get the forecast for the location key.
        try:
            forecasts_resp = await client.get(
                URL_FORECASTS_PATH.format(location_key=location_key),
                params={
                    URL_PARAM_API_KEY: API_KEY,
                },
            )
            forecast = forecasts_resp.json()["DailyForecasts"][0]
        except Exception:
            return []

        match forecast:
            case {
                "Link": url,
                "Temperature": {
                    "Maximum": {"Value": high, "Unit": temperature_unit},
                    "Minimum": {"Value": low},
                },
                "Day": {
                    "IconPhrase": day_summary,
                    "HasPrecipitation": day_precipitation,
                },
                "Night": {
                    "IconPhrase": night_summary,
                    "HasPrecipitation": night_precipitation,
                },
            }:
                return [
                    Suggestion(
                        title="Forecast",
                        url=url,
                        provider="accuweather",
                        score=SCORE,
                        icon=None,
                        city_name=location.get("LocalizedName"),
                        temperature_unit=temperature_unit,
                        high=high,
                        low=low,
                        day_summary=day_summary,
                        day_precipitation=day_precipitation,
                        night_summary=night_summary,
                        night_precipitation=night_precipitation,
                    )
                ]
            case _:
                logger.warning("Unexpected AccuWeather response")
                return []
