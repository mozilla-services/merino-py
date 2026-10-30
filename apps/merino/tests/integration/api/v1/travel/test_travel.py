# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/travel endpoint."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from merino.providers.travel.kayak.backends.protocol import TravelListing
from merino.providers.travel.kayak.provider import Provider as TravelProvider

TRAVEL_URL = "/api/v1/travel"


def test_travel_returns_listings_from_the_backend(client: TestClient, backend_mock: Any) -> None:
    """Serves the backend's listings, passing the query, default language, market and vertical through."""
    backend_mock.get_listings.return_value = [
        TravelListing(
            name="Charles de Gaulle Airport",
            full_name="Charles de Gaulle Airport, Paris, France (CDG)",
            type="airport",
            iata_code="CDG",
            place_id=1234,
            country="France",
        )
    ]

    response = client.get(TRAVEL_URL, params={"vertical": "flights", "q": "paris"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "Charles de Gaulle Airport",
            "full_name": "Charles de Gaulle Airport, Paris, France (CDG)",
            "type": "airport",
            "iata_code": "CDG",
            "place_id": 1234,
            "city_id": None,
            "country": "France",
        }
    ]
    backend_mock.get_listings.assert_called_once_with("paris", "en-US", "US", "flights")


def test_travel_passes_the_requested_market(client: TestClient, backend_mock: Any) -> None:
    """Forwards a client-provided market instead of the default."""
    response = client.get(TRAVEL_URL, params={"vertical": "flights", "q": "nyc", "market": "GB"})

    assert response.status_code == 200
    backend_mock.get_listings.assert_called_once_with("nyc", "en-US", "GB", "flights")


@pytest.mark.parametrize(
    ["accept_language", "expected"],
    [("fr-CA,en;q=0.8", "fr-CA"), ("en;q=0.5, de-DE;q=0.9", "de-DE")],
    ids=["first_language", "highest_quality"],
)
def test_travel_passes_the_accepted_language(
    client: TestClient, backend_mock: Any, accept_language: str, expected: str
) -> None:
    """Forwards the highest quality language from the `Accept-Language` header."""
    response = client.get(
        TRAVEL_URL,
        params={"vertical": "flights", "q": "nyc"},
        headers={"Accept-Language": accept_language},
    )

    assert response.status_code == 200
    backend_mock.get_listings.assert_called_once_with("nyc", expected, "US", "flights")


@pytest.mark.parametrize("q", ["a" * 2, "a" * 64])
def test_travel_accepts_query_length_bounds(client: TestClient, q: str) -> None:
    """Accepts queries at the minimum and maximum allowed lengths."""
    response = client.get(TRAVEL_URL, params={"vertical": "cars", "q": q})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"q": "paris"},
        {"vertical": "boats", "q": "paris"},
        {"vertical": "hotels"},
        {"vertical": "hotels", "q": "p"},
        {"vertical": "hotels", "q": "a" * 65},
        {"vertical": "hotels", "q": "paris", "market": "USA"},
        {"vertical": "hotels", "q": "paris", "market": "U"},
        {"vertical": "hotels", "q": "paris", "market": "1A"},
    ],
    ids=[
        "missing_vertical",
        "invalid_vertical",
        "missing_q",
        "q_too_short",
        "q_too_long",
        "market_too_long",
        "market_too_short",
        "market_non_alpha",
    ],
)
def test_travel_rejects_invalid_params(
    client: TestClient, backend_mock: Any, params: dict[str, str]
) -> None:
    """Returns 400 for missing or invalid query params without calling the backend."""
    response = client.get(TRAVEL_URL, params=params)

    assert response.status_code == 400
    backend_mock.get_listings.assert_not_called()


def test_travel_returns_empty_list_when_provider_disabled(
    client: TestClient, travel_provider: TravelProvider, backend_mock: Any
) -> None:
    """Returns an empty list without calling the backend when the provider is disabled."""
    travel_provider._enabled = False

    response = client.get(TRAVEL_URL, params={"vertical": "hotels", "q": "paris"})

    assert response.status_code == 200
    assert response.json() == []
    backend_mock.get_listings.assert_not_called()
