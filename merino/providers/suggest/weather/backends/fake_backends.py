"""Test backend for the Weather provider."""

from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.protocol import WeatherReport


class FakeWeatherBackend:  # pragma: no cover
    """A fake backend that always returns empty results."""

    async def get_weather_report(self, geolocation: Location) -> WeatherReport | None:
        """Fake Backend return nothing"""
        return None

    async def shutdown(self) -> None:
        """Fake Backend does not need to clean up
        any open connections.
        """
        pass
