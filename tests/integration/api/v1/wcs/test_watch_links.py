# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/watch-links`."""

import json
import pytest

from fastapi.testclient import TestClient
from typing import Any


_PATH = "/api/v1/wcs/watch-links"


@pytest.fixture()
def expected_us_en_us():
    """Return the expected WatchLinks for a US user with Accept-Language: en-US.

    your_region entries are drawn from WATCH_LINKS for the United States,
    sorted by sort_order then product_name ascending.

    other_regions entries come from all other countries whose streams pass the
    in_production and show_in_other_regions filters, sorted by display code
    ascending. Streams within each country sort by product_name then sort_order.
    """
    with open("tests/data/wcs/watch_links_response_en_us.json") as f:
        return json.load(f)


def test_watch_links_no_geolocation_returns_empty_response(client: TestClient) -> None:
    """Both sections are empty when geolocation is not available."""
    response = client.get(_PATH, headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert response.json() == {"your_region": [], "other_regions": []}
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_watch_links_with_geolocation_returns_populated_response(
    client: TestClient, inject_us_location: None
) -> None:
    """With US geolocation, both sections are populated."""
    response = client.get(_PATH, headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["your_region"]) > 0
    assert len(body["other_regions"]) > 0


def test_watch_links_us_en_us(
    client: TestClient,
    inject_us_location: None,
    expected_us_en_us: dict[str, Any],
) -> None:
    """Watch links for a US user with en-US language return the correct your_region and other_regions."""
    response = client.get(_PATH, headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    body = response.json()
    assert body == expected_us_en_us
    total_links = len(body["your_region"]) + sum(
        len(country["streams"]) for country in body["other_regions"]
    )
    assert total_links == 76


def test_watch_links_de_de(
    client: TestClient,
    inject_de_location: None,
) -> None:
    """Watch links for a German user with de language.

    your_region returns the five German streams sorted by sort_order then product_name.
    other_regions includes USA (with all seven qualifying US streams) but excludes GER.
    """
    response = client.get(_PATH, headers={"Accept-Language": "de"})

    assert response.status_code == 200
    body = response.json()

    # your_region: German streams sorted by sort_order ASC, product_name ASC
    assert body["your_region"] == [
        {
            "product_name": "FIFA+ (DAZN)",
            "entitlement": "Free and Paid",
            "url": "https://www.dazn.com/competition/Competition:50kvbmxi5r9amj2e39hznggqj",
        },
        {
            "product_name": "ARD",
            "entitlement": "Free",
            "url": "https://www.ardmediathek.de/live",
        },
        {
            "product_name": "SPORTSCHAU",
            "entitlement": "Free",
            "url": "https://www.sportschau.de/fussball/fifa-wm-2026/",
        },
        {
            "product_name": "ZDF",
            "entitlement": "Free",
            "url": "https://www.zdf.de/live-tv",
        },
        {
            "product_name": "MagentaTV",
            "entitlement": "Paid",
            "url": "https://www.telekom.de/sport/magenta-tv-fussball",
        },
    ]

    # Germany must not appear in other_regions (it is the user's own country)
    other_codes = [country["country_code"] for country in body["other_regions"]]
    assert "Germany" not in other_codes

    # United States must appear in other_regions with all seven qualifying streams
    usa_entry = next(
        country for country in body["other_regions"] if country["country_code"] == "United States"
    )
    assert usa_entry["streams"] == [
        {
            "product_name": "DirecTV",
            "entitlement": "Free Trial",
            "url": "https://www.directv.com/sports-info/soccer/worldcup",
        },
        {
            "product_name": "FOX ONE",
            "entitlement": "Free Trial",
            "url": "https://www.fox.com/soccer/fifa-world-cup",
        },
        {
            "product_name": "Fubo",
            "entitlement": "Free Trial",
            "url": "https://www.fubo.tv/stream/worldcup/",
        },
        {
            "product_name": "Hulu",
            "entitlement": "Free Trial",
            "url": "https://www.hulu.com/soccer",
        },
        {
            "product_name": "Peacock",
            "entitlement": "Paid",
            "url": "https://www.peacocktv.com/es-us/sports/copa-mundial#ib-section-section-6",
        },
        {
            "product_name": "Tubi",
            "entitlement": "Free",
            "url": "https://tubitv.com/hubs/fifa-world-cup-fox-hub",
        },
        {
            "product_name": "YouTube TV",
            "entitlement": "Free Trial",
            "url": "https://tv.youtube.com/browse/UCgL1z0K3r-CJig5sXlSvDbg",
        },
    ]

    # United States sorts last (alphabetically after United Kingdom)
    assert other_codes[-1] == "United States"

    total_links = len(body["your_region"]) + sum(
        len(country["streams"]) for country in body["other_regions"]
    )
    assert total_links == 76


def test_watch_links_de_en(
    client: TestClient,
    inject_de_location: None,
) -> None:
    """German users with a non-German browser language still see all five German streams.

    All DE streams are country-wide ('*') so the Accept-Language header does not
    gate them out.
    """
    response = client.get(_PATH, headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    body = response.json()

    your_region_names = [s["product_name"] for s in body["your_region"]]
    assert "FIFA+ (DAZN)" in your_region_names
    assert "ZDF" in your_region_names
    assert "ARD" in your_region_names
    assert "SPORTSCHAU" in your_region_names
    assert "MagentaTV" in your_region_names
    assert len(body["your_region"]) == 5
