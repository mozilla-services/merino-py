# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with a weather
provider.
"""

import logging
from logging import LogRecord
from typing import Any
from unittest.mock import AsyncMock
from starlette.types import ASGIApp, Scope

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pydantic import HttpUrl, TypeAdapter
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.middleware.user_agent import UserAgent
from merino.providers.suggest.weather.backends.accuweather.errors import (
    AccuweatherError,
    AccuweatherErrorMessages,
)
from merino.configs import settings
from merino.exceptions import BackendError, CacheAdapterError
from merino.middleware import ScopeKey
from merino.middleware.geolocation import GeolocationMiddleware, Location, Coordinates
from merino.providers.suggest.base import SuggestionRequest
from merino.providers.suggest.weather.backends.accuweather.errors import MissingLocationKeyError
from merino.providers.suggest.weather.backends.protocol import (
    CurrentConditions,
    Forecast,
    LocationCompletion,
    LocationCompletionGeoDetails,
    Temperature,
    WeatherBackend,
    WeatherReport,
)
from merino.providers.suggest.weather.provider import (
    LocationCompletionSuggestion,
    Provider,
    Suggestion,
)
from tests.integration.api.v1.types import Providers
from tests.types import FilterCaplogFixture

DEFAULT_SUGGESTIONS_RESPONSE_TTL_SEC = 300


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WeatherBackend mock object for test."""
    backend_mock = mocker.AsyncMock(spec=WeatherBackend)
    yield backend_mock


@pytest.fixture(name="geolocation_middleware")
def fixture_geolocation_middleware(mocker: MockerFixture) -> GeolocationMiddleware:
    """Create a GeolocationMiddleware object for test."""
    asgiapp_mock = mocker.AsyncMock(spec=ASGIApp)
    return GeolocationMiddleware(asgiapp_mock)


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any, statsd_mock: Any) -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "weather": Provider(
            backend=backend_mock,
            metrics_client=statsd_mock,
            score=0.3,
            name="test_weather",
            query_timeout_sec=0.2,
            enabled_by_default=True,
            cron_interval_sec=100,
        )
    }


@pytest.fixture(name="geolocation_scope")
def mock_scope() -> Scope:
    """Create a Scope mock object for Geolocation Middleware"""
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/suggest",
        "headers": [],
    }


@pytest.fixture(name="location_completion_sample_cities")
def fixture_location_completion_sample_cities() -> list[dict[str, Any]]:
    """Create a list of sample location completions for the search term 'new'"""
    return [
        {
            "Version": 1,
            "Key": "349727",
            "Type": "City",
            "Rank": 15,
            "LocalizedName": "New York",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NY", "LocalizedName": "New York"},
        },
        {
            "Version": 1,
            "Key": "348585",
            "Type": "City",
            "Rank": 35,
            "LocalizedName": "New Orleans",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "LA", "LocalizedName": "Louisiana"},
        },
        {
            "Version": 1,
            "Key": "349530",
            "Type": "City",
            "Rank": 35,
            "LocalizedName": "Newark",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NJ", "LocalizedName": "New Jersey"},
        },
        {
            "Version": 1,
            "Key": "331967",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newport Beach",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "CA", "LocalizedName": "California"},
        },
        {
            "Version": 1,
            "Key": "327357",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Haven",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "CT", "LocalizedName": "Connecticut"},
        },
        {
            "Version": 1,
            "Key": "333575",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Bedford",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "MA", "LocalizedName": "Massachusetts"},
        },
        {
            "Version": 1,
            "Key": "338640",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newton",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "MA", "LocalizedName": "Massachusetts"},
        },
        {
            "Version": 1,
            "Key": "339713",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "New Rochelle",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "NY", "LocalizedName": "New York"},
        },
        {
            "Version": 1,
            "Key": "336210",
            "Type": "City",
            "Rank": 45,
            "LocalizedName": "Newport News",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "VA", "LocalizedName": "Virginia"},
        },
        {
            "Version": 1,
            "Key": "2626691",
            "Type": "City",
            "Rank": 55,
            "LocalizedName": "Near Eastside",
            "Country": {"ID": "US", "LocalizedName": "United States"},
            "AdministrativeArea": {"ID": "IN", "LocalizedName": "Indiana"},
        },
    ]


@pytest.fixture(name="weather_report")
def fixture_weather_report() -> WeatherReport:
    """Fixture as a weather report."""
    return WeatherReport(
        city_name="Milton",
        region_code="WA",
        current_conditions=CurrentConditions(
            url=HttpUrl(
                "http://www.accuweather.com/en/us/milton-wa/98354/current-weather/"
                "41512_pc?lang=en-us"
            ),
            summary="Mostly sunny",
            icon_id=2,
            temperature=Temperature(c=-3.0, f=27.0),
        ),
        forecast=Forecast(
            url=HttpUrl(
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
        ttl=500,
    )


@pytest.fixture(name="expected_suggestion")
def fixture_expected_suggestion(weather_report: WeatherReport) -> list[Suggestion]:
    """Fixture as an expected suggestion."""
    return [
        Suggestion(
            title="Weather for Milton",
            url=HttpUrl(
                "http://www.accuweather.com/en/us/milton-wa/98354/current-weather/"
                "41512_pc?lang=en-us"
            ),
            provider="test_weather",
            is_sponsored=False,
            score=0.3,
            icon=None,
            city_name=weather_report.city_name,
            region_code=weather_report.region_code,
            current_conditions=weather_report.current_conditions,
            forecast=weather_report.forecast,
        )
    ]


def test_suggest_with_weather_report(
    client: TestClient,
    backend_mock: Any,
    weather_report: WeatherReport,
    expected_suggestion: list[Suggestion],
) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    supplies a suggestion.
    """
    backend_mock.get_weather_report.return_value = weather_report

    response = client.get("/api/v1/suggest?q=weather&request_type=weather")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, max-age=500"
    result = response.json()
    assert expected_suggestion == TypeAdapter(list[Suggestion]).validate_python(
        result["suggestions"]
    )


def test_suggest_without_weather_report(client: TestClient, backend_mock: Any) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    cannot supply a suggestion.
    """
    backend_mock.get_weather_report.return_value = None

    response = client.get("/api/v1/suggest?q=weather&request_type=weather")

    assert response.status_code == 200


def test_suggest_backend_error_weather_report_returns_empty(
    client: TestClient, backend_mock: Any
) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    cannot supply a suggestion.
    """
    expected_suggestion: list[Suggestion] = []
    backend_mock.get_weather_report.side_effect = BackendError()

    response = client.get("/api/v1/suggest?q=weather&request_type=weather")

    assert response.status_code == 200
    result = response.json()
    assert result["suggestions"] == expected_suggestion


def test_circuit_breaker_with_backend_error(
    client: TestClient,
    backend_mock: Any,
    mocker: MockerFixture,
    weather_report: WeatherReport,
    expected_suggestion: list[Suggestion],
) -> None:
    """Test that the accuweather provider can behave as expected when the circuit breaker
    is triggered.
    """
    backend_mock.get_weather_report.side_effect = AccuweatherError(
        AccuweatherErrorMessages.CACHE_READ_ERROR, exception=CacheAdapterError()
    )

    with freeze_time("2025-04-11") as freezer:
        # Trigger the breaker by calling the endpoint for the `threshold` times.
        for _ in range(settings.providers.accuweather.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?provider=accuweather&q=weather&request_type=weather")

        spy = mocker.spy(backend_mock, "get_weather_report")

        # Make a few more requests and verify all of them get short circuited and served by the fallback function.
        for _ in range(settings.providers.accuweather.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?provider=accuweather&q=weather&request_type=weather")

        # You shall not pass!
        spy.assert_not_called()

        # Now tick the timer to advance for the recovery timeout seconds.
        freezer.tick(settings.providers.accuweather.circuit_breaker_recover_timeout_sec + 1.0)

        # Clear the side effect to restore the normal behavior.
        backend_mock.get_weather_report.side_effect = None
        backend_mock.get_weather_report.return_value = weather_report

        # The breaker should be `half-open` hence the request should hit the integration point,
        # and bring the breaker back to the `closed` state.
        response = client.get("/api/v1/suggest?q=weather&request_type=weather")

        spy.assert_called_once()
        assert response.status_code == 200
        result = response.json()
        assert expected_suggestion == TypeAdapter(list[Suggestion]).validate_python(
            result["suggestions"]
        )

        # Verify that all the subsequent requests can succeed as well.
        for _ in range(settings.providers.accuweather.circuit_breaker_failure_threshold):
            response = client.get(
                "/api/v1/suggest?provider=accuweather&q=weather&request_type=weather"
            )

            assert response.status_code == 200
            result = response.json()
            assert expected_suggestion == TypeAdapter(list[Suggestion]).validate_python(
                result["suggestions"]
            )


def test_suggest_location_error_weather_report_returns_empty(
    client: TestClient, backend_mock: Any
) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    cannot supply a suggestion.
    """
    backend_mock.get_weather_report.side_effect = MissingLocationKeyError()

    response = client.get("/api/v1/suggest?q=weather&request_type=weather")

    assert response.status_code == 204


def test_suggest_weather_with_missing_request_type_query_parameter(client: TestClient) -> None:
    """Test that the suggest endpoint response for accuweather provider returns a 400 when `q`
    is present but `request_type is missing
    """
    response = client.get("/api/v1/suggest?q=weather&providers=weather")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid query parameters: `request_type` is missing"


@freeze_time("1998-03-31")
def test_providers_request_log_data_weather(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    client: TestClient,
) -> None:
    """Test that accuweather" provider logs are not using "web.suggest.request"."""
    caplog.set_level(logging.INFO)

    client.get("/api/v1/suggest?providers=accuweather&q=")

    suggest_records: list[LogRecord] = filter_caplog(caplog.records, "web.suggest.request")
    assert len(suggest_records) == 0


def test_suggest_with_location_completion(
    client: TestClient, backend_mock: Any, location_completion_sample_cities
) -> None:
    """Test that the suggest endpoint response is as expected when the Weather provider
    supplies a location completion.
    """
    location_completion: list[LocationCompletion] = [
        LocationCompletion(
            key=location["Key"],
            rank=location["Rank"],
            type=location["Type"],
            localized_name=location["LocalizedName"],
            country=LocationCompletionGeoDetails(
                id=location["Country"]["ID"],
                localized_name=location["Country"]["LocalizedName"],
            ),
            administrative_area=LocationCompletionGeoDetails(
                id=location["AdministrativeArea"]["ID"],
                localized_name=location["AdministrativeArea"]["LocalizedName"],
            ),
        )
        for location in location_completion_sample_cities
    ]

    expected_suggestion: list[LocationCompletionSuggestion] = [
        LocationCompletionSuggestion(
            title="Location completions",
            url=HttpUrl(url="https://merino.services.mozilla.com/"),
            provider="test_weather",
            is_sponsored=False,
            score=0.3,
            icon=None,
            locations=location_completion,
        )
    ]

    backend_mock.get_location_completion.return_value = location_completion

    response = client.get(
        url="/api/v1/suggest",
        params={"q": "new", "providers": "weather", "request_type": "location"},
    )

    assert response.status_code == 200
    result = response.json()
    assert expected_suggestion == TypeAdapter(list[LocationCompletionSuggestion]).validate_python(
        result["suggestions"]
    )


def test_suggest_with_location_completion_with_empty_search_term(
    client: TestClient,
) -> None:
    """Test that the suggest endpoint response returns empty location_completion when the q
    param (search_term) is an empty string
    """
    response = client.get(
        url="/api/v1/suggest",
        params={"q": "", "providers": "weather", "request_type": "location"},
    )
    expected_suggestion = response.json()["suggestions"][0]["locations"]

    assert response.status_code == 200
    assert expected_suggestion == []


def test_suggest_with_location_completion_with_incorrect_request_type_param(
    client: TestClient,
) -> None:
    """Test that the suggest endpoint response does not return a response when the request_type
    query param is invalid.
    """
    response = client.get(
        url="/api/v1/suggest",
        params={"q": "new", "providers": "weather", "request_type": "unsupported"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("city", "region", "country"),
    [
        (None, "MA", "US"),
        ("Boston", None, None),
        (None, "MA", None),
        (None, None, "US"),
        ("Boston", "MA,AA", None),
        ("Boston", None, "US"),
    ],
    ids=[
        "missing_city",
        "missing_region_and_country",
        "missing_city_and_country",
        "missing_city_and_region",
        "missing_country",
        "missing_regions",
    ],
)
@pytest.mark.asyncio
async def test_suggest_weather_with_incomplete_city_region_country_params(
    client: TestClient,
    city: str | None,
    region: str | None,
    country: str | None,
) -> None:
    """Test that the suggest endpoint response for accuweather provider returns a 400 when city, region
    & country params or city, regions & country are not all provided.
    """
    base_url = "/api/v1/suggest?q=weather&providers=weather&request_type=weather"

    if city is not None:
        base_url += f"&city={city}"
    if region is not None:
        base_url += f"&region={region}"
    if country is not None:
        base_url += f"&country={country}"

    response = client.get(base_url)
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Invalid query parameters: `city`, `region`, and `country` are either all present or all omitted."
    )


@pytest.mark.asyncio
async def test_suggest_weather_with_custom_location(
    client: TestClient,
    geolocation_middleware: GeolocationMiddleware,
    geolocation_scope: Scope,
    providers: Providers,
    mocker: MockerFixture,
) -> None:
    """Test that the suggest endpoint returns a response using custom city, region & country params when provided."""
    expected_initial_location: Location = Location(
        country="US",
        country_name="United States",
        regions=["WA"],
        region_names=["Washington"],
        city="Milton",
        dma=819,
        postal_code="98354",
        coordinates=Coordinates(latitude=47.2513, longitude=-122.3149, radius=22),
        city_names={"en": "Milton", "ru": "Мильтон"},
    )

    receive_mock = AsyncMock()
    send_mock = AsyncMock()

    mock_query = mocker.patch.object(providers["weather"], "query", autospec=True)

    # IP points to city = Milton, region = WA, country = US
    mocker.patch("merino.middleware.geolocation.CLIENT_IP_OVERRIDE", "216.160.83.56")

    await geolocation_middleware(geolocation_scope, receive_mock, send_mock)

    assert geolocation_scope[ScopeKey.GEOLOCATION] == expected_initial_location

    response = client.get(
        "/api/v1/suggest",
        params={
            "q": "",
            "providers": "weather",
            "request_type": "weather",
            "city": "Boston",
            "region": "MA",
            "country": "US",
            "source": "newtab",
        },
    )

    expected_geolocation = geolocation_scope[ScopeKey.GEOLOCATION].model_copy(
        update={"city": "Boston", "regions": ["MA"], "country": "US"}
    )

    mock_query.assert_called_with(
        SuggestionRequest(
            query="",
            geolocation=expected_geolocation,
            request_type="weather",
            languages=["en-US"],
            user_agent=UserAgent(browser="Other", form_factor="other", os_family="other"),
            source="newtab",
        )
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_suggest_weather_with_custom_location_with_admin_codes(
    client: TestClient,
    geolocation_middleware: GeolocationMiddleware,
    geolocation_scope: Scope,
    providers: Providers,
    mocker: MockerFixture,
) -> None:
    """Test that the suggest endpoint returns a response using custom city, admin1, admin2 & country params when provided."""
    expected_initial_location: Location = Location(
        country="US",
        country_name="United States",
        regions=["WA"],
        region_names=["Washington"],
        city="Milton",
        dma=819,
        postal_code="98354",
        coordinates=Coordinates(latitude=47.2513, longitude=-122.3149, radius=22),
        city_names={"en": "Milton", "ru": "Мильтон"},
    )

    receive_mock = AsyncMock()
    send_mock = AsyncMock()

    mock_query = mocker.patch.object(providers["weather"], "query", autospec=True)

    # IP points to city = Milton, region = WA, country = US
    mocker.patch("merino.middleware.geolocation.CLIENT_IP_OVERRIDE", "216.160.83.56")

    await geolocation_middleware(geolocation_scope, receive_mock, send_mock)

    assert geolocation_scope[ScopeKey.GEOLOCATION] == expected_initial_location

    response = client.get(
        "/api/v1/suggest",
        params={
            "q": "",
            "providers": "weather",
            "request_type": "weather",
            "city": "Boston",
            "region": "MA,AA",
            "country": "US",
            "source": "newtab",
        },
    )
    expected_geolocation = geolocation_scope[ScopeKey.GEOLOCATION].model_copy(
        update={"city": "Boston", "regions": ["MA", "AA"], "country": "US"}
    )
    mock_query.assert_called_with(
        SuggestionRequest(
            query="",
            geolocation=expected_geolocation,
            request_type="weather",
            languages=["en-US"],
            user_agent=UserAgent(browser="Other", form_factor="other", os_family="other"),
            source="newtab",
        )
    )

    assert response.status_code == 200
