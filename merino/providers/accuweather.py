"""AccuWeather integration."""
import logging
from typing import Any, Optional
from urllib.parse import urlencode, urlunparse

import httpx
from fastapi import FastAPI, Request

from merino.config import settings
from merino.middleware.geolocation import ctxvar_geolocation
from merino.providers.base import BaseProvider, BaseSuggestion

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

    _app: Optional[FastAPI]

    def __init__(
        self, app: FastAPI = None, enabled_by_default: bool = False, **kwargs: Any
    ) -> None:
        self._app = app
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize the provider."""
        ...

    def hidden(self) -> bool:  # noqa: D102
        return False

    async def handle_request(self, request: Request) -> list[BaseSuggestion]:
        """Provide suggestions for a given request."""
        suggestions = await self.query()
        return suggestions

    async def query(self) -> list[BaseSuggestion]:
        """Provide suggestions that don't depend on a client query string."""
        api_key = settings.providers.accuweather.api_key
        if api_key == "":
            logger.warning("AccuWeather API key not specified")
            return []

        location = ctxvar_geolocation.get()
        country = location.country
        postal_code = location.postal_code
        if country is None or postal_code is None:
            logger.warning("Country and/or postal code unknown")
            return []

        base_url = settings.providers.accuweather.url_base
        async with httpx.AsyncClient(app=self._app, base_url=base_url) as client:
            suggestions = await self._get_forecast(
                client,
                api_key=api_key,
                country=country,
                postal_code=postal_code,
            )
            return suggestions

    async def _get_forecast(
        self, client: httpx.AsyncClient, api_key: str, country: str, postal_code: str
    ) -> list[BaseSuggestion]:
        aw = settings.providers.accuweather

        # Get the AccuWeather location key for the country and postal codes.
        location_url = urlunparse(
            (
                "",
                "",
                aw.url_postalcodes_path.format(country_code=country),
                "",
                urlencode(
                    {
                        aw.url_postalcodes_param_query: postal_code,
                        aw.url_param_key: api_key,
                    }
                ),
                "",
            )
        )
        try:
            location_resp = await client.get(location_url)
            location = location_resp.json()[0]
            location_key = location["Key"]
        except Exception:
            return []

        # Get the forecast for the location key.
        forecasts_url = urlunparse(
            (
                "",
                "",
                aw.url_forecasts_path.format(location_key=location_key),
                "",
                urlencode(
                    {
                        aw.url_param_key: api_key,
                    }
                ),
                "",
            )
        )
        try:
            forecasts_resp = await client.get(forecasts_url)
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
                        score=aw.score,
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

        logger.warning("Unexpected AccuWeather response")
        return []
