# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/weather/hourly-forecasts endpoint."""

from typing import Any

import freezegun
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.providers.suggest.weather.backends.accuweather.errors import (
    AccuweatherError,
    AccuweatherErrorMessages,
    MissingLocationKeyError,
)
from merino.providers.suggest.weather.backends.protocol import (
    HourlyForecastsWithTTL,
)


def test_hourly_forecasts_endpoint_success(
    client: TestClient,
    backend_mock: Any,
    hourly_forecasts_with_ttl: HourlyForecastsWithTTL,
) -> None:
    """Test that hourly forecasts endpoint returns forecasts successfully."""
    backend_mock.get_hourly_forecasts.return_value = hourly_forecasts_with_ttl

    response = client.get("/api/v1/weather/hourly-forecasts")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, max-age=3600"

    result = response.json()
    assert len(result) == 5
    assert result[0]["date_time"] == "2026-02-18T14:00:00-05:00"
    assert result[0]["temperature"]["f"] == 60
    assert result[0]["temperature"]["c"] == 16
    assert result[0]["icon_id"] == 6


def test_hourly_forecasts_endpoint_missing_location(
    client: TestClient,
    backend_mock: Any,
) -> None:
    """Test endpoint handles missing location gracefully."""
    backend_mock.get_hourly_forecasts.side_effect = MissingLocationKeyError()

    response = client.get("/api/v1/weather/hourly-forecasts")

    # Provider catches the exception and returns None
    # Endpoint returns empty list with max-age=0
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["Cache-Control"] == "private, max-age=0"


def test_hourly_forecasts_with_custom_location(
    client: TestClient,
    backend_mock: Any,
    hourly_forecasts_with_ttl: HourlyForecastsWithTTL,
) -> None:
    """Test endpoint with custom location parameters."""
    backend_mock.get_hourly_forecasts.return_value = hourly_forecasts_with_ttl

    response = client.get(
        "/api/v1/weather/hourly-forecasts",
        params={"city": "San Francisco", "region": "CA", "country": "US"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, max-age=3600"

    result = response.json()
    assert len(result) == 5
    assert result[0]["temperature"]["f"] == 60
    assert result[0]["temperature"]["c"] == 16


def test_hourly_forecasts_missing_required_location_params(
    client: TestClient,
) -> None:
    """Test endpoint returns 400 when location params are incomplete."""
    # Missing country (only city and region provided)
    response = client.get(
        "/api/v1/weather/hourly-forecasts", params={"city": "Boston", "region": "MA"}
    )

    assert response.status_code == 400
    assert "city" in response.json()["detail"].lower()


def test_circuit_breaker_with_backend_error(
    client: TestClient,
    backend_mock: Any,
    mocker: MockerFixture,
    hourly_forecasts_with_ttl: HourlyForecastsWithTTL,
) -> None:
    """Test that the circuit breaker opens after repeated backend failures and recovers
    after the timeout.
    """
    backend_mock.get_hourly_forecasts.side_effect = AccuweatherError(
        AccuweatherErrorMessages.CACHE_READ_HOURLY_FORECAST_ERROR,
        exception=CacheAdapterError(),
    )

    with freezegun.freeze_time("2025-04-11") as freezer:
        # Trigger the breaker — the endpoint catches AccuweatherError gracefully, so
        # these return 200 [] while the circuit breaker counts each failure.
        for _ in range(settings.providers.accuweather.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/weather/hourly-forecasts")

        spy = mocker.spy(backend_mock, "get_hourly_forecasts")

        # While the circuit is open the fallback returns None — endpoint returns empty list.
        for _ in range(settings.providers.accuweather.circuit_breaker_failure_threshold):
            response = client.get("/api/v1/weather/hourly-forecasts")
            assert response.status_code == 200
            assert response.json() == []
            assert response.headers["Cache-Control"] == "private, max-age=0"

        spy.assert_not_called()

        # Advance time past the recovery timeout.
        freezer.tick(settings.providers.accuweather.circuit_breaker_recover_timeout_sec + 1.0)

        # Restore normal behavior.
        backend_mock.get_hourly_forecasts.side_effect = None
        backend_mock.get_hourly_forecasts.return_value = hourly_forecasts_with_ttl

        # The breaker should be half-open — this request hits the backend and closes it.
        response = client.get("/api/v1/weather/hourly-forecasts")

        spy.assert_called_once()
        assert response.status_code == 200
        assert len(response.json()) == 5
