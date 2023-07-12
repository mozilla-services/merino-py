# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with a weather
provider.
"""
import logging
from logging import LogRecord
from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pydantic import TypeAdapter
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.exceptions import BackendError
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherBackend,
    WeatherReport,
)
from merino.providers.weather.provider import Provider, Suggestion
from merino.utils.log_data_creators import RequestSummaryLogDataModel
from tests.integration.api.types import RequestSummaryLogDataFixture
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WeatherBackend mock object for test."""
    backend_mock = mocker.AsyncMock(spec=WeatherBackend)
    yield backend_mock


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any, statsd_mock: Any) -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "weather": Provider(
            backend=backend_mock,
            metrics_client=statsd_mock,
            score=0.3,
            name="weather",
            query_timeout_sec=0.2,
            enabled_by_default=True,
        )
    }


def test_suggest_with_weather_report(client: TestClient, backend_mock: Any) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    supplies a suggestion.
    """
    weather_report: WeatherReport = WeatherReport(
        city_name="Milton",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/milton-wa/98354/current-weather/"
                "41512_pc?lang=en-us"
            ),
            summary="Mostly sunny",
            icon_id=2,
            temperature=Temperature(c=-3.0, f=27.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/milton-wa/98354/"
                "daily-weather-forecast/41512_pc?lang=en-us"
            ),
            summary=(
                "Snow tomorrow evening accumulating 1-2 inches, then changing to ice "
                "and continuing into Friday morning"
            ),
            high=Temperature(c=-1.7, f=29.0),
            low=Temperature(c=-7.8, f=18.0),
        ),
    )
    expected_suggestion: list[Suggestion] = [
        Suggestion(
            title="Weather for Milton",
            url=(
                "http://www.accuweather.com/en/us/milton-wa/98354/current-weather/"
                "41512_pc?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=0.3,
            icon=None,
            city_name=weather_report.city_name,
            current_conditions=weather_report.current_conditions,
            forecast=weather_report.forecast,
        )
    ]
    backend_mock.get_weather_report.return_value = weather_report

    response = client.get("/api/v1/suggest?q=weather")

    assert response.status_code == 200
    result = response.json()
    assert expected_suggestion == TypeAdapter(list[Suggestion]).validate_python(
        result["suggestions"]
    )


def test_suggest_without_weather_report(client: TestClient, backend_mock: Any) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    cannot supply a suggestion.
    """
    expected_suggestion: list[Suggestion] = []
    backend_mock.get_weather_report.return_value = None

    response = client.get("/api/v1/suggest?q=weather")

    assert response.status_code == 200
    result = response.json()
    assert result["suggestions"] == expected_suggestion


def test_suggest_weather_backend_error(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
    backend_mock: Any,
) -> None:
    """Test that the suggest endpoint response is as expected and that a warning is
    logged when the Weather provider receives an error from the backend.
    """
    expected_suggestion: list[Suggestion] = []
    expected_log_messages: list[dict[str, str]] = [
        {"levelname": "WARNING", "message": "Could not generate a weather report"}
    ]
    backend_mock.get_weather_report.side_effect = BackendError(
        expected_log_messages[0]["message"]
    )

    response = client.get("/api/v1/suggest?q=weather")

    assert response.status_code == 200
    result = response.json()
    assert result["suggestions"] == expected_suggestion

    actual_log_messages: list[dict[str, str]] = [
        {"levelname": record.levelname, "message": record.message}
        for record in filter_caplog(caplog.records, "merino.providers.weather.provider")
    ]
    assert actual_log_messages == expected_log_messages


@freeze_time("1998-03-31")
def test_providers_request_log_data_weather(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: RequestSummaryLogDataFixture,
    client: TestClient,
) -> None:
    """Test that accuweather" provider logs using "request.summary"."""
    caplog.set_level(logging.INFO)

    expected_log_data: RequestSummaryLogDataModel = RequestSummaryLogDataModel(
        agent="testclient",
        path="/api/v1/suggest",
        method="GET",
        querystring={"providers": "accuweather", "q": ""},
        errno=0,
        code=200,
        time="1998-03-31T00:00:00",
    )

    client.get("/api/v1/suggest?providers=accuweather&q=")

    records: list[LogRecord] = filter_caplog(caplog.records, "request.summary")
    assert len(records) == 1

    suggest_records: list[LogRecord] = filter_caplog(
        caplog.records, "web.suggest.request"
    )
    assert len(suggest_records) == 0

    record: LogRecord = records[0]
    log_data: RequestSummaryLogDataModel = extract_request_summary_log_data(record)
    assert log_data == expected_log_data
