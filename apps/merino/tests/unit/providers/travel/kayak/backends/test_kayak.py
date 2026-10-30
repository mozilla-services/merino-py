# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Kayak backend module."""

import logging
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, ConnectTimeout, Request, Response
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.providers.travel.kayak.backends.kayak import KayakBackend
from merino.providers.travel.kayak.backends.protocol import TravelListing, TravelVertical
from tests.types import FilterCaplogFixture

API_KEY = "test-api-key"
AUTOCOMPLETE_URL = "https://affiliate-en-us.kayakaffiliates.com/api/affiliate/autocomplete/v1"
FLIGHTS_URL = f"{AUTOCOMPLETE_URL}/flights"
HOTELS_URL = f"{AUTOCOMPLETE_URL}/hotels"
CARS_URL = f"{AUTOCOMPLETE_URL}/cars"


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


def kayak_hotel_place() -> dict[str, Any]:
    """Return a Kayak hotels autocomplete result for a hotel, which has no IATA code."""
    return {
        "placeId": 61746,
        "primaryPlaceType": "hotel",
        "displayPlaceType": {"type": "hotel", "displayName": "Hotel"},
        "name": "Four Seasons Hotel Las Vegas",
        "fullName": "Four Seasons Hotel Las Vegas, Las Vegas",
        "location": {"latitude": 36.09024, "longitude": -115.17246},
        "places": ["Las Vegas"],
        "entityKey": "khotel:61746",
        "hotelName": "Four Seasons Hotel Las Vegas",
        "countryName": "United States",
        "countryCode": "US",
        "regionName": "Nevada",
        "cityName": "Las Vegas",
        "cityId": 15830,
        "hotelId": 12345,
    }


def kayak_car_place() -> dict[str, Any]:
    """Return a Kayak cars autocomplete result, which has no `name` field."""
    return {
        "placeId": 59560,
        "primaryPlaceType": "city",
        "displayPlaceType": {"type": "city", "displayName": "City"},
        "fullName": "New York, United States",
        "location": {"latitude": 40.7128, "longitude": -74.006},
        "countryName": "United States",
        "countryCode": "US",
        "regionName": "New York",
        "cityName": "New York",
        "cityId": 15830,
    }


def kayak_response(json: Any, status_code: int = 200, url: str = FLIGHTS_URL) -> Response:
    """Return an HTTP response from the Kayak autocomplete endpoint."""
    return Response(status_code=status_code, json=json, request=Request(method="GET", url=url))


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
async def test_get_listings_hotels_success(
    kayak: KayakBackend, http_client: AsyncMock, statsd_mock: Any
) -> None:
    """Calls the hotels endpoint and maps hotel results, keeping those without an IATA code."""
    http_client.get.return_value = kayak_response(
        {"results": [kayak_hotel_place()]}, url=HOTELS_URL
    )

    listings = await kayak.get_listings("las vegas", "en-US", "US", "hotels")

    assert listings == [
        TravelListing(
            name="Four Seasons Hotel Las Vegas",
            full_name="Four Seasons Hotel Las Vegas, Las Vegas",
            type="hotel",
            iata_code=None,
            place_id=61746,
            city_id=15830,
            country="United States",
            hotel_id=12345,
            entity_key="khotel:61746",
        )
    ]
    http_client.get.assert_called_once_with(
        HOTELS_URL, params={"apiKey": API_KEY, "searchTerm": "las vegas"}
    )
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.success")


@pytest.mark.asyncio
async def test_get_listings_cars_success(
    kayak: KayakBackend, http_client: AsyncMock, statsd_mock: Any
) -> None:
    """Calls the cars endpoint and falls back to the full name for results without a name."""
    http_client.get.return_value = kayak_response({"results": [kayak_car_place()]}, url=CARS_URL)

    listings = await kayak.get_listings("new york", "en-US", "US", "cars")

    assert listings == [
        TravelListing(
            name="New York, United States",
            full_name="New York, United States",
            type="city",
            place_id=59560,
            city_id=15830,
            country="United States",
        )
    ]
    http_client.get.assert_called_once_with(
        CARS_URL, params={"apiKey": API_KEY, "searchTerm": "new york"}
    )
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


@pytest.mark.parametrize("vertical", ["flights", "hotels", "cars"])
@pytest.mark.asyncio
async def test_get_listings_returns_at_most_six_listings(
    kayak: KayakBackend, http_client: AsyncMock, vertical: TravelVertical
) -> None:
    """Caps the number of listings at six."""
    # mock return value set to return 10 objects in the array
    http_client.get.return_value = kayak_response(
        {"results": [kayak_place(place_id) for place_id in range(10)]}
    )

    listings = await kayak.get_listings("new york", "en-US", "US", vertical)

    assert [listing.place_id for listing in listings] == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("vertical", ["flights", "hotels", "cars"])
@pytest.mark.asyncio
async def test_get_listings_empty_results(
    kayak: KayakBackend, http_client: AsyncMock, statsd_mock: Any, vertical: TravelVertical
) -> None:
    """Returns an empty list and records a success when Kayak has no matching places."""
    http_client.get.return_value = kayak_response({"results": []})

    listings = await kayak.get_listings("zzzz", "en-US", "US", vertical)

    assert listings == []
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.success")


@pytest.mark.parametrize(
    ["status_code", "body"],
    [
        (400, "Validation error in request"),
        (401, "Missing or incorrect API key"),
        (403, "Request is not allowed"),
        (404, "Resource was not found"),
        (500, "Internal server error"),
    ],
    ids=["bad_request", "unauthorized", "forbidden", "not_found", "server_error"],
)
@pytest.mark.asyncio
async def test_get_listings_http_error(
    kayak: KayakBackend,
    http_client: AsyncMock,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    status_code: int,
    body: str,
) -> None:
    """Returns an empty list and logs a warning without the API key on an HTTP error."""
    caplog.set_level(logging.WARNING)
    http_client.get.return_value = kayak_response(body, status_code)

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == []
    records = filter_caplog(caplog.records, "merino.providers.travel.kayak.backends.kayak")
    assert [record.message for record in records] == ["Kayak autocomplete request failed"]
    assert API_KEY not in caplog.text
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.failed")


@pytest.mark.asyncio
async def test_get_listings_transport_error(
    kayak: KayakBackend,
    http_client: AsyncMock,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Returns an empty list and logs a warning when the request to Kayak times out."""
    caplog.set_level(logging.WARNING)
    http_client.get.side_effect = ConnectTimeout("Connection timed out")

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == []
    records = filter_caplog(caplog.records, "merino.providers.travel.kayak.backends.kayak")
    assert [record.message for record in records] == ["Kayak autocomplete request failed"]
    statsd_mock.increment.assert_called_once_with("kayak.request.autocomplete.failed")


@pytest.mark.parametrize(
    ["vertical", "json"],
    [
        ("flights", {}),
        ("flights", {"results": None}),
        ("flights", {"results": ["not a place"]}),
        ("flights", {"results": [{"iataCode": "JFK"}]}),
        ("hotels", {"results": ["not a place"]}),
        ("cars", {"results": [{**kayak_car_place(), "fullName": None}]}),
    ],
    ids=[
        "missing_results",
        "null_results",
        "result_not_an_object",
        "result_missing_fields",
        "hotel_result_not_an_object",
        "car_result_without_full_name",
    ],
)
@pytest.mark.asyncio
async def test_get_listings_invalid_response(
    kayak: KayakBackend,
    http_client: AsyncMock,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    vertical: TravelVertical,
    json: Any,
) -> None:
    """Returns an empty list and logs a warning when the response has an unexpected shape."""
    caplog.set_level(logging.WARNING)
    http_client.get.return_value = kayak_response(json)

    listings = await kayak.get_listings("new york", "en-US", "US", vertical)

    assert listings == []
    records = filter_caplog(caplog.records, "merino.providers.travel.kayak.backends.kayak")
    assert [record.message for record in records] == [
        "Kayak autocomplete response has incorrect shape"
    ]
    statsd_mock.increment.assert_called_once_with("kayak.response.invalid")


@pytest.mark.asyncio
async def test_get_listings_non_json_response(
    kayak: KayakBackend, http_client: AsyncMock, statsd_mock: Any
) -> None:
    """Returns an empty list when Kayak responds with a body that is not JSON."""
    http_client.get.return_value = Response(
        status_code=200, text="<html></html>", request=Request(method="GET", url=FLIGHTS_URL)
    )

    listings = await kayak.get_listings("new york", "en-US", "US", "flights")

    assert listings == []
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
