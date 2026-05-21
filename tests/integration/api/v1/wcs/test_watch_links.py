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
    """Return the expected WatchLinks for a US user with Accept-Language: en-US.

    your_region entries are drawn from WATCH_LINKS for the United States,
    sorted by sort_order then product_name ascending.

    other_regions entries come from all other countries whose streams pass the
    in_production and show_in_other_regions filters, sorted by display code
    ascending. Streams within each country sort by product_name then sort_order.
    """
    return {
        "your_region": [
            {
                "product_name": "FIFA+",
                "entitlement": "Free and Paid",
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
                "country_code": "ARG",
                "streams": [
                    {
                        "product_name": "Paramount+",
                        "entitlement": "Paid",
                        "url": "https://www.paramountplus.com/ar/",
                    },
                    {
                        "product_name": "Pluto TV",
                        "entitlement": "Free Trial",
                        "url": "https://pluto.tv/latam/live-tv/66997d18a1b69e00082ee85f?lang=en",
                    },
                    {
                        "product_name": "TVP",
                        "entitlement": "Free",
                        "url": "https://www.tvpublica.com.ar/",
                    },
                ],
            },
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
                    {
                        "product_name": "ServusTV",
                        "entitlement": "Paid",
                        "url": "https://www.servustv.com/de/epg",
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
                "country_code": "BRA",
                "streams": [
                    {
                        "product_name": "CazéTV - YouTube",
                        "entitlement": "Free",
                        "url": "https://www.youtube.com/@CazeTV/streams",
                    },
                    {
                        "product_name": "Globoplay",
                        "entitlement": "Free and Paid",
                        "url": "https://globoplay.globo.com/tv-globo/ao-vivo/6120663/",
                    },
                    {
                        "product_name": "SBT",
                        "entitlement": "Free",
                        "url": "https://mais.sbt.com.br/",
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
                        "product_name": "Crave",
                        "entitlement": "Paid",
                        "url": "https://www.crave.ca/en/ctv",
                    },
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
                    {
                        "product_name": "DGO",
                        "entitlement": "Paid",
                        "url": "https://www.directvgo.com/cl/home",
                    },
                    {
                        "product_name": "Paramount+",
                        "entitlement": "Paid",
                        "url": "https://www.paramountplus.com/cl/",
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
                        "product_name": "DIRECTV",
                        "entitlement": "Paid",
                        "url": "https://www.directvla.com/co/mundial",
                    },
                    {
                        "product_name": "Ditu",
                        "entitlement": "Free and Paid",
                        "url": "https://ditu.caracoltv.com/category/copa-mundial-de-futbol-2026",
                    },
                    {
                        "product_name": "Win Play",
                        "entitlement": "Paid",
                        "url": "https://winplay.co/co/futbol-internacional",
                    },
                ],
            },
            {
                "country_code": "CZE",
                "streams": [
                    {
                        "product_name": "Nova Action",
                        "entitlement": "Free",
                        "url": "https://tv.nova.cz/sledujte-zive/1-nova",
                    },
                    {
                        "product_name": "iVysílání",
                        "entitlement": "Free",
                        "url": "https://sport.ceskatelevize.cz/zive-vysilani",
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
                    {
                        "product_name": "TV 2 Play",
                        "entitlement": "Paid",
                        "url": "https://play.tv2.dk/sport",
                    },
                ],
            },
            {
                "country_code": "ECU",
                "streams": [
                    {
                        "product_name": "Paramount+",
                        "entitlement": "Paid",
                        "url": "https://www.paramountplus.com/ec/",
                    },
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
                    {
                        "product_name": "beIN SPORTS",
                        "entitlement": "Paid",
                        "url": "https://connect.beinsports.com/france/",
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
                        "product_name": "MagentaTV",
                        "entitlement": "Paid",
                        "url": "https://www.telekom.de/sport/magenta-tv-fussball",
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
                "country_code": "HUN",
                "streams": [
                    {
                        "product_name": "M4sport",
                        "entitlement": "Free",
                        "url": "https://m4sport.hu/elo/mtv4live/",
                    },
                    {
                        "product_name": "MÉDIAKLIKK",
                        "entitlement": "Free",
                        "url": "https://mediaklikk.hu/elo/dunalive/",
                    },
                ],
            },
            {
                "country_code": "INA",
                "streams": [
                    {
                        "product_name": "TVRI Klik",
                        "entitlement": "Free",
                        "url": "https://klik.tvri.go.id/detailchannel/TVRI_CH_03",
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
                        "product_name": "DAZN",
                        "entitlement": "Paid",
                        "url": "https://www.dazn.com/it-IT/",
                    },
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
                    {
                        "product_name": "TV 2 Play",
                        "entitlement": "Paid",
                        "url": "https://www.tv2.no/livesport/fotball/turneringer/fifa-fotball-vm/a315b842-f4bc-5687-9ecb-3e06d6acdf9a/oversikt",
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
                "country_code": "POL",
                "streams": [
                    {
                        "product_name": "TVP SPORT",
                        "entitlement": "Free",
                        "url": "https://sport.tvp.pl/transmisje",
                    },
                ],
            },
            {
                "country_code": "POR",
                "streams": [
                    {
                        "product_name": "LiveModeTV - YouTube",
                        "entitlement": "Free",
                        "url": "https://www.youtube.com/@LiveModeTV_PT",
                    },
                    {
                        "product_name": "sport tv",
                        "entitlement": "Free and Paid",
                        "url": "https://www.sporttv.pt/mundial-fifa-2026",
                    },
                ],
            },
            {
                "country_code": "ROU",
                "streams": [
                    {
                        "product_name": "AntenaPLAY",
                        "entitlement": "Paid",
                        "url": "https://antenaplay.ro/fifa-world-cup",
                    },
                ],
            },
            {
                "country_code": "RSA",
                "streams": [
                    {
                        "product_name": "DStv Stream",
                        "entitlement": "Paid",
                        "url": "https://dstv.stream/#/",
                    },
                    {
                        "product_name": "SABC+",
                        "entitlement": "Free",
                        "url": "https://sabc-plus.com/live",
                    },
                ],
            },
            {
                "country_code": "SRB",
                "streams": [
                    {
                        "product_name": "Arena Cloud",
                        "entitlement": "Free Trial",
                        "url": "https://webtv.arenacloudtv.com/",
                    },
                    {
                        "product_name": "RTS Planeta",
                        "entitlement": "Free and Paid",
                        "url": "https://rtsplaneta.rs/live/tv",
                    },
                ],
            },
            {
                "country_code": "SUI",
                "streams": [
                    {
                        "product_name": "RSI",
                        "entitlement": "Free",
                        "url": "https://www.rsi.ch/play/tv/streaming",
                    },
                    {
                        "product_name": "RTS",
                        "entitlement": "Free",
                        "url": "https://www.rts.ch/play/tv/rts-livestreams",
                    },
                    {
                        "product_name": "SRF",
                        "entitlement": "Free",
                        "url": "https://www.srf.ch/play/tv/sport-livestreams",
                    },
                ],
            },
            {
                "country_code": "SVK",
                "streams": [
                    {
                        "product_name": "JOJPLAY",
                        "entitlement": "Paid",
                        "url": "https://play.joj.sk/",
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
            "product_name": "FIFA+",
            "entitlement": "Free and Paid",
            "url": "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
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

    # GER must not appear in other_regions (it is the user's own country)
    other_codes = [country["country_code"] for country in body["other_regions"]]
    assert "GER" not in other_codes

    # USA must appear in other_regions with all seven qualifying streams
    usa_entry = next(country for country in body["other_regions"] if country["country_code"] == "USA")
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

    # USA sorts last (display code "USA" > "UK" alphabetically)
    assert other_codes[-1] == "USA"

    total_links = len(body["your_region"]) + sum(
        len(country["streams"]) for country in body["other_regions"]
    )
    assert total_links == 76
