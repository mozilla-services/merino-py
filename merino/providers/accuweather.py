"""AccuWeather integration."""
import logging
import os
from typing import Any, Optional
from urllib.parse import urlencode, urlunparse

import httpx
from fastapi import FastAPI, Request

from merino.config import settings
from merino.providers.base import BaseProvider, BaseSuggestion

logger = logging.getLogger(__name__)


def get_value(d: dict, keys: list, default_value: Any = None) -> Any:
    """Get a nested value in a sequence of dictionaries."""
    for k in keys:
        if d is None or not isinstance(d, dict):
            return default_value
        d = d.get(k)
    return d


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

    _app: FastAPI

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
        api_key = os.environ.get("MERINO_ACCUWEATHER_API_KEY")
        if api_key is None:
            logger.warning("AccuWeather API key not specified")
            return []

        country = None
        postal_code = None
        try:
            country = request.state.location.country
            postal_code = request.state.location.postal_code
        except AttributeError:
            logger.warning("Country and/or postal codes unknown")
            return []

        suggestions = await self.query(api_key, country, postal_code)
        return suggestions

    async def query(
        self, api_key: str, country: str, postal_code: str
    ) -> list[BaseSuggestion]:
        """Provide suggestions for a given postal code."""
        base_url = settings.providers.accuweather.api_base_url
        async with httpx.AsyncClient(app=self._app, base_url=base_url) as client:
            suggestions = await self._get_forecast(
                client, api_key=api_key, country=country, postal_code=postal_code
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
                aw.api_postalcodes_path.format(country_code=country),
                "",
                urlencode(
                    {
                        aw.api_postalcodes_param_query: postal_code,
                        aw.api_param_key: api_key,
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
                aw.api_forecasts_path.format(location_key=location_key),
                "",
                urlencode(
                    {
                        aw.api_param_key: api_key,
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

        return [
            Suggestion(
                title="Forecast",
                url=forecast.get("Link"),
                provider="accuweather",
                score=aw.score,
                icon=None,
                city_name=location.get("LocalizedName"),
                temperature_unit=get_value(
                    forecast, ["Temperature", "Maximum", "Unit"]
                ),
                high=get_value(forecast, ["Temperature", "Maximum", "Value"]),
                low=get_value(forecast, ["Temperature", "Minimum", "Value"]),
                day_summary=get_value(forecast, ["Day", "IconPhrase"]),
                day_precipitation=get_value(forecast, ["Day", "HasPrecipitation"]),
                night_summary=get_value(forecast, ["Night", "IconPhrase"]),
                night_precipitation=get_value(forecast, ["Night", "HasPrecipitation"]),
            )
        ]
