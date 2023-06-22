"""Test backend for the Weather provider."""
from typing import Optional

from merino.middleware.geolocation import Location
from merino.providers.weather.backends.protocol import WeatherReport


class FakeWeatherBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def get_weather_report(
        self, geolocation: Location
    ) -> Optional[WeatherReport]:
        """Fake Backend return nothing"""
        return None

    async def shutdown(self) -> None:
        """Fake Backend does not need to clean up
        any open connections.
        """
        pass
