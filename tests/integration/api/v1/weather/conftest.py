# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for weather API endpoint tests."""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from pydantic import HttpUrl

from merino.configs import settings
from merino.providers.suggest.weather.backends.protocol import (
    HourlyForecast,
    HourlyForecastsWithTTL,
    Temperature,
    WeatherBackend,
)
from merino.providers.suggest.weather.provider import Provider
from merino.providers.suggest import get_weather_provider
from merino.main import app


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WeatherBackend mock object for test."""
    backend_mock = mocker.AsyncMock(spec=WeatherBackend)
    return backend_mock


@pytest.fixture(name="weather_provider")
def fixture_weather_provider(backend_mock: Any, statsd_mock: Any) -> Provider:
    """Create a weather provider with mocked backend."""
    return Provider(
        backend=backend_mock,
        metrics_client=statsd_mock,
        score=0.3,
        name="test_weather",
        query_timeout_sec=0.2,
        enabled_by_default=True,
        cron_interval_sec=100,
    )


@pytest.fixture(name="hourly_forecasts_with_ttl")
def fixture_hourly_forecasts_with_ttl() -> HourlyForecastsWithTTL:
    """Fixture for hourly forecasts with TTL."""
    ttl = settings.providers.accuweather.cache_ttls.hourly_forecast_ttl_sec

    hourly_forecasts = [
        HourlyForecast(
            date_time=f"2026-02-18T{14+i:02d}:00:00-05:00",
            epoch_date_time=1708281600 + (i * 3600),
            temperature=Temperature(f=60 + i),
            icon_id=6,
            url=HttpUrl(
                f"http://www.accuweather.com/en/us/san-francisco/94105/"
                f"hourly-weather-forecast/39376?day=1&hbhhour={14+i}&lang=en-us"
            ),
        )
        for i in range(5)
    ]

    return HourlyForecastsWithTTL(hourly_forecasts=hourly_forecasts, ttl=ttl)


@pytest.fixture(name="inject_weather_provider", autouse=True)
def fixture_inject_weather_provider(weather_provider: Provider):
    """Inject the weather provider into the app for testing."""

    def get_test_weather_provider() -> Provider:
        return weather_provider

    app.dependency_overrides[get_weather_provider] = get_test_weather_provider
    yield
    del app.dependency_overrides[get_weather_provider]
