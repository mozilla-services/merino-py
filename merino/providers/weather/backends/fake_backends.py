"""Test backend for the Weather provider."""
from typing import Optional

from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import WeatherReport


class FakeWeatherBackend:
    """A fake backend that always returns empty results."""

    async def get_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:
        """Fake Backend return nothing"""
        return None
