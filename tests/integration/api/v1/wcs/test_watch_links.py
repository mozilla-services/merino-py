# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/watch-links`."""

from typing import Any

import pytest
from fastapi.testclient import TestClient


_PATH = "/api/v1/wcs/watch-links"


@pytest.fixture
def expected_us_en_us() -> dict[str, Any]:
    """Return the expected WatchLinksResponse for a US user with Accept-Language: en-US.

    your_region entries are drawn from wcs_watch_links_filtered.csv for the United States,
    sorted by sort_order then product_name ascending.

    other_regions entries come from all other countries whose streams pass the
    in_production and show_vpn_regions filters, grouped by country and sorted by
    display code ascending. Streams within each country sort by product_name then sort_order.
    """
    return {
        "your_region": [
            {
                "product_name": "FIFA+",
                "entitlement": "FIFA+",
                "url": "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            },
            {
                "product_name": "Tubi",
                "entitlement": "Free",
                "url": "https://tubitv.com/hubs/fifa-world-cup-fox-hub",
            },
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
                "product_name": "YouTube TV",
                "entitlement": "Free Trial",
                "url": "https://tv.youtube.com/browse/UCgL1z0K3r-CJig5sXlSvDbg",
            },
            {
                "product_name": "Peacock",
                "entitlement": "Paid",
                "url": "https://www.peacocktv.com/es-us/sports/copa-mundial#ib-section-section-6",
            },
        ],
        "other_regions": [
            # all countries sorted by display code A-Z; streams by product_name then sort_order
            {
                "country_code": "AUS",
                "streams": [
                    {
                        "product_name": "SBS On Demand",
                        "entitlement": "Free",
                        "url": "https://www.sbs.com.au/ondemand/watch/1726824003663",
                    },
                ],
            },
            {
                "country_code": "AUT",
                "streams": [
                    {
                        "product_name": "ORF",
                        "entitlement": "Free",
                        "url": "https://on.orf.at/live",
                    },
                ],
            },
            {
                "country_code": "BEL",
                "streams": [
                    {
                        "product_name": "RTBF",
                        "entitlement": "Free",
                        "url": "https://auvio.rtbf.be/categorie/football-11",
                    },
                    {
                        "product_name": "VRT 1",
                        "entitlement": "Free",
                        "url": "https://www.vrt.be/vrtmax/kanalen/sporza/",
                    },
                ],
            },
            {
                "country_code": "BUL",
                "streams": [
                    {"product_name": "BNT", "entitlement": "Free", "url": "https://tv.bnt.bg/"},
                ],
            },
            {
                "country_code": "CAN",
                "streams": [
                    {
                        "product_name": "RDS",
                        "entitlement": "Free and Paid",
                        "url": "https://www.rds.ca/soccer/coupe-du-monde/",
                    },
                    {
                        "product_name": "TSN",
                        "entitlement": "Free and Paid",
                        "url": "https://www.tsn.ca/soccer/fifa-world-cup/",
                    },
                ],
            },
            {
                "country_code": "CHI",
                "streams": [
                    {
                        "product_name": "Chilevision",
                        "entitlement": "Free",
                        "url": "https://www.chilevision.cl/senal-online/",
                    },
                ],
            },
            {
                "country_code": "COL",
                "streams": [
                    {
                        "product_name": "Canal RCN",
                        "entitlement": "Free",
                        "url": "https://www.canalrcn.com/co/deportes",
                    },
                    {
                        "product_name": "Ditu",
                        "entitlement": "Free and Paid",
                        "url": "https://ditu.caracoltv.com/category/copa-mundial-de-futbol-2026",
                    },
                ],
            },
            {
                "country_code": "DEN",
                "streams": [
                    {
                        "product_name": "DRTV",
                        "entitlement": "Free",
                        "url": "https://www.dr.dk/drtv/kategorier/sport",
                    },
                ],
            },
            {
                "country_code": "ECU",
                "streams": [
                    {
                        "product_name": "Teleamazonas",
                        "entitlement": "Free",
                        "url": "https://www.teleamazonas.com/teleamazonas-en-vivo/",
                    },
                ],
            },
            {
                "country_code": "ESP",
                "streams": [
                    {
                        "product_name": "DAZN",
                        "entitlement": "Free Trial",
                        "url": "https://www.dazn.com/es-ES/",
                    },
                    {
                        "product_name": "RTVE",
                        "entitlement": "Free",
                        "url": "https://www.rtve.es/play/videos/copa-mundial-de-la-fifa-2026/",
                    },
                ],
            },
            {
                "country_code": "FIN",
                "streams": [
                    {
                        "product_name": "MTV Katsomo",
                        "entitlement": "Free and Paid",
                        "url": "https://www.mtv.fi/ohjelmat/fifa-2026",
                    },
                    {
                        "product_name": "Yle Areena",
                        "entitlement": "Free and Paid",
                        "url": "https://areena.yle.fi/1-72511886",
                    },
                ],
            },
            {
                "country_code": "FRA",
                "streams": [
                    {
                        "product_name": "M6+",
                        "entitlement": "Free",
                        "url": "https://www.m6.fr/coupe-du-monde-2026-p_26649",
                    },
                ],
            },
            {
                "country_code": "GER",
                "streams": [
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
                ],
            },
            {
                "country_code": "IRL",
                "streams": [
                    {
                        "product_name": "RTÉ Player",
                        "entitlement": "Free",
                        "url": "https://www.rte.ie/player/onnow",
                    },
                ],
            },
            {
                "country_code": "ITA",
                "streams": [
                    {
                        "product_name": "RaiPlay",
                        "entitlement": "Free",
                        "url": "https://www.raiplay.it/programmi/mondialidicalcio2026",
                    },
                ],
            },
            {
                "country_code": "MEX",
                "streams": [
                    {
                        "product_name": "Azteca Deportes",
                        "entitlement": "Free",
                        "url": "https://envivo.tvazteca.com/",
                    },
                    {
                        "product_name": "ViX",
                        "entitlement": "Free and Paid",
                        "url": "https://vix.com/es-es/canales",
                    },
                ],
            },
            {
                "country_code": "NED",
                "streams": [
                    {"product_name": "NOS", "entitlement": "Free", "url": "https://nos.nl/live"},
                    {
                        "product_name": "NPO",
                        "entitlement": "Free",
                        "url": "https://npo.nl/start/live",
                    },
                ],
            },
            {
                "country_code": "NOR",
                "streams": [
                    {
                        "product_name": "NRK TV",
                        "entitlement": "Free",
                        "url": "https://tv.nrk.no/serie/fifa-fotball-vm-2026",
                    },
                ],
            },
            {
                "country_code": "NZL",
                "streams": [
                    {
                        "product_name": "TVNZ+",
                        "entitlement": "Free and Paid",
                        "url": "https://www.tvnz.co.nz/competition/fifa-2026",
                    },
                ],
            },
            {
                "country_code": "POR",
                "streams": [
                    {
                        "product_name": "sport tv",
                        "entitlement": "Free and Paid",
                        "url": "https://www.sporttv.pt/mundial-fifa-2026",
                    },
                ],
            },
            {
                "country_code": "RSA",
                "streams": [
                    {
                        "product_name": "SABC+",
                        "entitlement": "Free",
                        "url": "https://sabc-plus.com/live",
                    },
                ],
            },
            {
                "country_code": "SWE",
                "streams": [
                    {
                        "product_name": "SVT Play",
                        "entitlement": "Free and Paid",
                        "url": "https://www.svtplay.se/fifa-fotbolls-vm-2026",
                    },
                    {
                        "product_name": "TV4 Play",
                        "entitlement": "Free and Paid",
                        "url": "https://www.tv4play.se/kategorier/fifa-fotbolls-vm-2026",
                    },
                ],
            },
            {
                "country_code": "UK",
                "streams": [
                    {
                        "product_name": "BBC iPlayer",
                        "entitlement": "Free",
                        "url": "https://www.bbc.co.uk/iplayer/episodes/m002gjj0/fifa-world-cup-2026",
                    },
                    {
                        "product_name": "ITVX",
                        "entitlement": "Free",
                        "url": "https://www.itv.com/watch",
                    },
                    {
                        "product_name": "STV Player",
                        "entitlement": "Free",
                        "url": "https://player.stv.tv/live",
                    },
                ],
            },
        ],
    }


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
    assert total_links == 43
