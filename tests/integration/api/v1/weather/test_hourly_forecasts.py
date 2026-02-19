# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/weather/hourly-forecasts endpoint."""

from typing import Any

from fastapi.testclient import TestClient

from merino.providers.suggest.weather.backends.accuweather.errors import MissingLocationKeyError
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
    assert result[0]["temperature"]["c"] == 16  # Auto-converted from F: round((60-32)*5/9)


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
