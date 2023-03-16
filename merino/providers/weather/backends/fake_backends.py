"""Test backend for the Weather provider."""
from typing import Optional

from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import WeatherReport


class FakeWeatherBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    def cache_inputs_for_weather_report(self, geolocation: Location) -> Optional[bytes]:
        """Doesn't return any cache key inputs."""
        return None

    async def get_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:
        """Fake Backend return nothing"""
        return None
