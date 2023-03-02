# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather provider module."""

from typing import Any, cast

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture
from redis.asyncio import Redis, RedisError

from merino.cache.redis import RedisAdapter
from merino.config import settings
from merino.exceptions import BackendError
from merino.middleware.geolocation import Location
from merino.providers.base import BaseSuggestion, SuggestionRequest
from merino.providers.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    Temperature,
    WeatherBackend,
    WeatherReport,
)
from merino.providers.weather.provider import Provider, Suggestion
from tests.types import FilterCaplogFixture


@pytest.fixture(name="geolocation")
def fixture_geolocation() -> Location:
    """Return a test Location."""
    return Location(
        country="US",
        region="CA",
        city="San Francisco",
        dma=807,
        postal_code="94105",
    )


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WeatherBackend mock object for test."""
    return mocker.AsyncMock(spec=WeatherBackend)


@pytest.fixture(name="redis_mock")
def fixture_redis_mock(mocker: MockerFixture) -> Any:
    """Create a Redis client mock object for testing."""
    return mocker.AsyncMock(spec=Redis)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any, redis_mock: Any, statsd_mock: Any) -> Provider:
    """Create a weather Provider for test."""
    return Provider(
        backend=backend_mock,
        cache=RedisAdapter(redis_mock),
        metrics_client=statsd_mock,
        name="weather",
        score=0.3,
        query_timeout_sec=0.2,
        cached_report_ttl_sec=10,
    )


def test_enabled_by_default(provider: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert provider.enabled_by_default is False


def test_not_hidden_by_default(provider: Provider) -> None:
    """Test for the hidden method."""
    assert provider.hidden() is False


@pytest.mark.asyncio
async def test_query_weather_report_returned(
    backend_mock: Any, provider: Provider, geolocation: Location
) -> None:
    """Test that the query method provides a valid weather suggestion."""
    report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
    )
    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for San Francisco",
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name=report.city_name,
            current_conditions=report.current_conditions,
            forecast=report.forecast,
        )
    ]
    backend_mock.cache_inputs_for_weather_report.return_value = None
    backend_mock.get_weather_report.return_value = report

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_no_weather_report_returned(
    backend_mock: Any, provider: Provider, geolocation: Location
) -> None:
    """Test that the query method doesn't provide a weather suggestion without a weather
    report.
    """
    expected_suggestions: list[Suggestion] = []
    backend_mock.cache_inputs_for_weather_report.return_value = None
    backend_mock.get_weather_report.return_value = None

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions


@pytest.mark.asyncio
async def test_query_error(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the query method logs a warning and doesn't provide a weather
    suggestion if the backend raises an error.
    """
    expected_suggestions: list[Suggestion] = []
    expected_log_messages: list[dict[str, str]] = [
        {"levelname": "WARNING", "message": "Could not generate a weather report"}
    ]
    backend_mock.cache_inputs_for_weather_report.return_value = None
    backend_mock.get_weather_report.side_effect = BackendError(
        expected_log_messages[0]["message"]
    )

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )

    assert suggestions == expected_suggestions
    actual_log_messages: list[dict[str, str]] = [
        {"levelname": record.levelname, "message": record.message}
        for record in filter_caplog(caplog.records, "merino.providers.weather.provider")
    ]
    assert actual_log_messages == expected_log_messages


@pytest.mark.asyncio
async def test_query_cached_weather_report(
    mocker: MockerFixture,
    redis_mock: Any,
    statsd_mock: Any,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that weather reports are cached in Redis after the first request to the backend."""
    cache_keys: dict[str, bytes] = {}

    async def mock_redis_get(key) -> Any:
        return cache_keys.get(key, None)

    redis_mock.get.side_effect = mock_redis_get

    async def mock_redis_set(key, value, **kwargs):
        cache_keys[key] = value

    redis_mock.set.side_effect = mock_redis_set

    report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
    )
    backend_mock.cache_inputs_for_weather_report.return_value = cast(
        str, geolocation.city
    ).encode("utf-8") + cast(str, geolocation.postal_code).encode("utf-8")
    backend_mock.get_weather_report.return_value = report

    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for San Francisco",
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name=report.city_name,
            current_conditions=report.current_conditions,
            forecast=report.forecast,
        )
    ]

    uncached_suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert uncached_suggestions == expected_suggestions

    cache_key = provider.cache_key_for_weather_report(geolocation)
    assert cache_key is not None
    redis_mock.get.assert_called_once_with(cache_key)
    statsd_mock.increment.assert_called_once_with("providers.weather.query.cache.miss")
    backend_mock.get_weather_report.assert_called_once()
    redis_mock.set.assert_called_once_with(
        cache_key, report.json().encode("utf-8"), ex=10
    )
    assert cache_keys[cache_key] is not None

    redis_mock.reset_mock()
    statsd_mock.reset_mock()
    backend_mock.reset_mock()

    cached_suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert cached_suggestions == expected_suggestions

    redis_mock.get.assert_called_once_with(cache_key)
    statsd_mock.increment.assert_called_once_with("providers.weather.query.cache.hit")
    backend_mock.get_weather_report.assert_not_called()
    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_query_cached_no_weather_report(
    mocker: MockerFixture,
    redis_mock: Any,
    statsd_mock: Any,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that the absence of a weather report for a location is cached in Redis, avoiding
    multiple requests to the backend.
    """
    cache_keys: dict[str, bytes] = {}

    async def mock_redis_get(key) -> Any:
        return cache_keys.get(key, None)

    redis_mock.get.side_effect = mock_redis_get

    async def mock_redis_set(key, value, **kwargs):
        cache_keys[key] = value

    redis_mock.set.side_effect = mock_redis_set

    backend_mock.cache_inputs_for_weather_report.return_value = cast(
        str, geolocation.city
    ).encode("utf-8") + cast(str, geolocation.postal_code).encode("utf-8")
    backend_mock.get_weather_report.return_value = None

    uncached_suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert uncached_suggestions == []

    cache_key = provider.cache_key_for_weather_report(geolocation)
    assert cache_key is not None
    redis_mock.get.assert_called_once_with(cache_key)
    statsd_mock.increment.assert_called_once_with("providers.weather.query.cache.miss")
    backend_mock.get_weather_report.assert_called_once()
    redis_mock.set.assert_called_once_with(cache_key, b"{}", ex=10)
    assert cache_keys[cache_key] is not None

    redis_mock.reset_mock()
    statsd_mock.reset_mock()
    backend_mock.reset_mock()

    cached_suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert cached_suggestions == []

    redis_mock.get.assert_called_once_with(cache_key)
    statsd_mock.increment.assert_called_once_with("providers.weather.query.cache.hit")
    backend_mock.get_weather_report.assert_not_called()
    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_query_with_bad_cache_entry(
    mocker: MockerFixture,
    redis_mock: Any,
    statsd_mock: Any,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that a bad cache entry causes the provider to make a request to the backend."""
    backend_mock.cache_inputs_for_weather_report.return_value = cast(
        str, geolocation.city
    ).encode("utf-8") + cast(str, geolocation.postal_code).encode("utf-8")
    cache_key = provider.cache_key_for_weather_report(geolocation)
    assert cache_key is not None

    cache_keys: dict[str, bytes] = {
        cache_key: b"badjson!",
    }

    async def mock_redis_get(key) -> Any:
        return cache_keys.get(key, None)

    redis_mock.get.side_effect = mock_redis_get

    async def mock_redis_set(key, value, **kwargs):
        cache_keys[key] = value

    redis_mock.set.side_effect = mock_redis_set

    report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
    )
    backend_mock.get_weather_report.return_value = report

    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for San Francisco",
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name=report.city_name,
            current_conditions=report.current_conditions,
            forecast=report.forecast,
        )
    ]

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert suggestions == expected_suggestions

    redis_mock.get.assert_called_once_with(cache_key)
    statsd_mock.increment.assert_called_once_with("providers.weather.query.cache.error")
    backend_mock.get_weather_report.assert_called_once()
    redis_mock.set.assert_called_once_with(
        cache_key, report.json().encode("utf-8"), ex=10
    )


@pytest.mark.asyncio
async def test_query_redis_unavailable(
    mocker: MockerFixture,
    redis_mock: Any,
    statsd_mock: Any,
    backend_mock: Any,
    provider: Provider,
    geolocation: Location,
) -> None:
    """Test that Redis errors don't prevent requests to the backend."""
    redis_mock.get.side_effect = RedisError("mercury in retrograde")
    redis_mock.set.side_effect = RedisError("synergies not aligned")

    report: WeatherReport = WeatherReport(
        city_name="San Francisco",
        current_conditions=CurrentConditions(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            summary="Mostly cloudy",
            icon_id=6,
            temperature=Temperature(c=15.5, f=60.0),
        ),
        forecast=Forecast(
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/daily-weather-forecast/39376_pc?lang=en-us"
            ),
            summary="Pleasant Saturday",
            high=Temperature(c=21.1, f=70.0),
            low=Temperature(c=13.9, f=57.0),
        ),
    )
    backend_mock.cache_inputs_for_weather_report.return_value = cast(
        str, geolocation.city
    ).encode("utf-8") + cast(str, geolocation.postal_code).encode("utf-8")
    backend_mock.get_weather_report.return_value = report

    expected_suggestions: list[Suggestion] = [
        Suggestion(
            title="Weather for San Francisco",
            url=(
                "http://www.accuweather.com/en/us/san-francisco-ca/"
                "94103/current-weather/39376_pc?lang=en-us"
            ),
            provider="weather",
            is_sponsored=False,
            score=settings.providers.accuweather.score,
            icon=None,
            city_name=report.city_name,
            current_conditions=report.current_conditions,
            forecast=report.forecast,
        )
    ]

    suggestions: list[BaseSuggestion] = await provider.query(
        SuggestionRequest(query="", geolocation=geolocation)
    )
    assert suggestions == expected_suggestions

    redis_mock.get.assert_called_once()
    backend_mock.get_weather_report.assert_called_once()
    redis_mock.set.assert_called_once()
    statsd_mock.increment.assert_has_calls(
        [
            mocker.call("providers.weather.query.cache.error"),
            mocker.call("providers.weather.query.cache.error"),
        ]
    )
