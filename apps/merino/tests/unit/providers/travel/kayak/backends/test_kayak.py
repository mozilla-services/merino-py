# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Kayak backend module."""

import logging
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Request, Response
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.providers.travel.kayak.backends.kayak import KayakBackend
from merino.providers.travel.kayak.backends.protocol import TravelListing
from tests.types import FilterCaplogFixture

API_KEY = "test-api-key"
FLIGHTS_URL = "https://affiliate-en-us.kayakaffiliates.com/api/affiliate/autocomplete/v1/flights"


def kayak_place(place_id: int, iata_code: str | None = "JFK") -> dict[str, Any]:
    """Return a Kayak flights autocomplete result, optionally without an IATA code."""
    place = {
        "placeId": place_id,
        "primaryPlaceType": "airport",
        "displayPlaceType": {"type": "airport", "displayName": "Airport"},
        "name": "John F Kennedy Intl",
        "fullName": "John F Kennedy Intl, New York, United States, (JFK)",
        "countryName": "United States",
        "regionName": "New York",
        "cityName": "New York",
        "isMetro": False,
    }
    if iata_code is not None:
        place["iataCode"] = iata_code
    return place


def kayak_response(json: Any, status_code: int = 200) -> Response:
    """Return an HTTP response from the Kayak flights autocomplete endpoint."""
    return Response(
        status_code=status_code, json=json, request=Request(method="GET", url=FLIGHTS_URL)
    )


@pytest.fixture(name="kayak")
def fixture_kayak_backend(mocker: MockerFixture, statsd_mock: Any) -> KayakBackend:
    """Kayak backend for testing."""
    return KayakBackend(
        api_key=API_KEY,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        url_base="https://affiliate-{language}-{market}.kayakaffiliates.com",
        url_autocomplete_path="/api/affiliate/autocomplete/v1/{vertical}",
        metrics_client=statsd_mock,
    )


@pytest.fixture(name="http_client")
def fixture_http_client(kayak: KayakBackend) -> AsyncMock:
    """Return the mocked HTTP client of the Kayak backend."""
    return cast(AsyncMock, kayak.http_client)


@pytest.mark.asyncio
async def test_get_listings_success(
    kayak: KayakBackend, http_client: AsyncMock, statsd_mock: Any
) -> None:
    """Calls Kayak with the API key and search term, and maps results to travel listings."""
    http_client.get.return_value = kayak_response({"results": [kayak_place(12345)]})

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == [
        TravelListing(
            name="John F Kennedy Intl",
            full_name="John F Kennedy Intl, New York, United States, (JFK)",
            type="airport",
            iata_code="JFK",
            place_id=12345,
            city_id=None,
            country="United States",
        )
    ]
    http_client.get.assert_called_once_with(
        FLIGHTS_URL, params={"apiKey": API_KEY, "searchTerm": "new york"}
    )
    statsd_mock.timeit.assert_called_once_with("kayak.request.autocomplete.get")
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.success")


@pytest.mark.asyncio
async def test_get_listings_drops_flights_without_iata_code(
    kayak: KayakBackend, http_client: AsyncMock
) -> None:
    """Skips flight results that are missing an IATA code."""
    http_client.get.return_value = kayak_response(
        {"results": [kayak_place(1, iata_code=None), kayak_place(2), kayak_place(3, "")]}
    )

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert [listing.place_id for listing in listings] == [2]


@pytest.mark.asyncio
async def test_get_listings_returns_at_most_six_listings(
    kayak: KayakBackend, http_client: AsyncMock
) -> None:
    """Caps the number of listings at six."""
    # mock return value set to return 10 objects in the array
    http_client.get.return_value = kayak_response(
        {"results": [kayak_place(place_id) for place_id in range(10)]}
    )

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert [listing.place_id for listing in listings] == [0, 1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_get_listings_http_error(
    kayak: KayakBackend,
    http_client: AsyncMock,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Returns an empty list and logs a warning without the API key on an HTTP error."""
    caplog.set_level(logging.WARNING)
    http_client.get.return_value = kayak_response("Missing or incorrect API key", 401)

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == []
    records = filter_caplog(caplog.records, "merino.providers.travel.kayak.backends.kayak")
    assert [record.message for record in records] == ["Kayak autocomplete request failed"]
    assert API_KEY not in caplog.text
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.failed")


@pytest.mark.parametrize(
    "json",
    [{}, {"results": ["not a place"]}, {"results": [{"iataCode": "JFK"}]}],
    ids=["missing_results", "result_not_an_object", "result_missing_fields"],
)
@pytest.mark.asyncio
async def test_get_listings_invalid_response(
    kayak: KayakBackend,
    http_client: AsyncMock,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    json: Any,
) -> None:
    """Returns an empty list and logs a warning when the response has an unexpected shape."""
    caplog.set_level(logging.WARNING)
    http_client.get.return_value = kayak_response(json)

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == []
    records = filter_caplog(caplog.records, "merino.providers.travel.kayak.backends.kayak")
    assert [record.message for record in records] == [
        "Kayak autocomplete response has incorrect shape"
    ]
    statsd_mock.increment.assert_called_once_with("kayak.response.invalid")


@pytest.mark.asyncio
async def test_get_listings_uses_language_and_market_in_url(
    kayak: KayakBackend, http_client: AsyncMock
) -> None:
    """Builds the Kayak host from the lowercased primary language subtag and market."""
    http_client.get.return_value = kayak_response({"results": []})

    await kayak.get_listings("london", "fr-CA", "GB", "flights")

    http_client.get.assert_called_once_with(
        "https://affiliate-fr-gb.kayakaffiliates.com/api/affiliate/autocomplete/v1/flights",
        params={"apiKey": API_KEY, "searchTerm": "london"},
    )


@pytest.mark.parametrize(
    ["language", "expected"],
    [
        ("en-US", "en"),
        ("FR", "fr"),
        ("fr-CA", "fr"),
        ("*", "en"),
        ("", "en"),
        ("en_US", "en"),
    ],
    ids=["language_and_region", "uppercase", "other_language", "wildcard", "empty", "underscore"],
)
def test_parse_language(language: str, expected: str) -> None:
    """Extracts the lowercase primary language subtag, with an `en` fallback."""
    assert KayakBackend._parse_language(language) == expected


@pytest.mark.asyncio
async def test_shutdown(kayak: KayakBackend, http_client: AsyncMock) -> None:
    """Closes the HTTP client on shutdown."""
    await kayak.shutdown()

    http_client.aclose.assert_awaited_once()
