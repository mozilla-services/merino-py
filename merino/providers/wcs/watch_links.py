"""Static watch link mapping keyed by ISO country code and language prefix."""

from typing import TypedDict
from pydantic import BaseModel, Field, HttpUrl


_SORT_ORDER_LABELS: dict[int, str] = {
    1: "Free and Paid",  # reserved for FIFA+ links; rank 1 pins them first in every region
    2: "Free",
    3: "Free and Paid",
    4: "Free Trial",
    5: "Paid",
}


class WatchLinkEntry(BaseModel):
    """A single streaming service entry for a country and language."""

    product_name: str = Field(description="Stream product name.")
    url: HttpUrl = Field(description="Direct stream URL.")
    sort_order: int = Field(
        description="Display sort order: 1=FIFA, 2=Free, 3=Free and Paid, 4=Free Trial, 5=Paid."
    )
    in_production: bool = Field(description="True when this stream is enabled in production.")
    show_in_other_regions: bool = Field(
        description="True when this stream should appear in the other regions list."
    )

    @property
    def entitlement(self) -> str:
        """Return the human-readable entitlement label for this entry."""
        return _SORT_ORDER_LABELS.get(self.sort_order, str(self.sort_order))


class CountryEntry(TypedDict):
    """Country-level watch link data with DAU and language-keyed stream lists."""

    dau: int
    langs: dict[str, list[WatchLinkEntry]]


_FIFA_PLUS = HttpUrl(
    "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f"
)


def build_watch_link(
    product_name: str,
    url: str,
    sort_order: int,
    *,
    in_production: bool,
    show_in_other_regions: bool,
) -> WatchLinkEntry:
    """Build a WatchLinkEntry from positional and keyword fields."""
    return WatchLinkEntry(
        product_name=product_name,
        url=HttpUrl(url),
        sort_order=sort_order,
        in_production=in_production,
        show_in_other_regions=show_in_other_regions,
    )


def _build_fifa_watch_link(*, show_in_other_regions: bool = False) -> WatchLinkEntry:
    """Build a FIFA+ entry reusing the shared showcase URL."""
    return WatchLinkEntry(
        product_name="FIFA+",
        url=_FIFA_PLUS,
        sort_order=1,
        in_production=True,
        show_in_other_regions=show_in_other_regions,
    )


# TODO: SUI has ??? from the source CSV

# Outer key: ISO 3166-1 alpha-2 country code.
# "langs" inner key: BCP 47 language prefix (e.g. "en", "de") or "*" for country-wide streams
# that apply regardless of language.
WATCH_LINKS: dict[str, CountryEntry] = {
    "AR": {
        "dau": 411_130,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TVP",
                    "https://www.tvpublica.com.ar/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Pluto TV",
                    "https://pluto.tv/latam/live-tv/66997d18a1b69e00082ee85f?lang=en",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/ar/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "AT": {
        "dau": 501_177,
        "langs": {
            "de": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "ORF",
                    "https://on.orf.at/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "ServusTV",
                    "https://www.servustv.com/de/epg",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "AU": {
        "dau": 593_227,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "SBS On Demand",
                    "https://www.sbs.com.au/ondemand/watch/1726824003663",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "BE": {
        "dau": 369_344,
        "langs": {
            "*": [
                _build_fifa_watch_link(),
            ],
            "fr": [
                build_watch_link(
                    "RTBF",
                    "https://auvio.rtbf.be/categorie/football-11",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
            "nl": [
                build_watch_link(
                    "VRT 1",
                    "https://www.vrt.be/vrtmax/kanalen/sporza/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "BG": {
        "dau": 173_120,
        "langs": {
            "bg": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "BNT",
                    "https://tv.bnt.bg/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "BR": {
        "dau": 1_923_018,
        "langs": {
            "pt": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "CazéTV - YouTube",
                    "https://www.youtube.com/@CazeTV/streams",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "SBT",
                    "https://mais.sbt.com.br/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Globoplay",
                    "https://globoplay.globo.com/tv-globo/ao-vivo/6120663/",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "CA": {
        "dau": 1_160_538,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TSN",
                    "https://www.tsn.ca/soccer/fifa-world-cup/",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "RDS",
                    "https://www.rds.ca/soccer/coupe-du-monde/",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Crave",
                    "https://www.crave.ca/en/ctv",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "CH": {
        "dau": 539_945,
        "langs": {
            "*": [
                _build_fifa_watch_link(),
            ],
            "de": [
                build_watch_link(
                    "SRF",
                    "https://www.srf.ch/play/tv/sport-livestreams",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
            "fr": [
                build_watch_link(
                    "RTS",
                    "https://www.rts.ch/play/tv/rts-livestreams",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
            "it": [
                build_watch_link(
                    "RSI",
                    "https://www.rsi.ch/play/tv/streaming",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "CL": {
        "dau": 189_362,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Chilevision",
                    "https://www.chilevision.cl/senal-online/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DGO",
                    "https://www.directvgo.com/cl/home",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/cl/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "CO": {
        "dau": 329_562,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Canal RCN",
                    "https://www.canalrcn.com/co/deportes",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Ditu",
                    "https://ditu.caracoltv.com/category/copa-mundial-de-futbol-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Win Play",
                    "https://winplay.co/co/futbol-internacional",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DIRECTV",
                    "https://www.directvla.com/co/mundial",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "CZ": {
        "dau": 481_742,
        "langs": {
            "cs": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "iVysílání",
                    "https://sport.ceskatelevize.cz/zive-vysilani",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Nova Action",
                    "https://tv.nova.cz/sledujte-zive/1-nova",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "DE": {
        "dau": 5_475_312,
        "langs": {
            "de": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "ZDF",
                    "https://www.zdf.de/live-tv",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "ARD",
                    "https://www.ardmediathek.de/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "SPORTSCHAU",
                    "https://www.sportschau.de/fussball/fifa-wm-2026/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "MagentaTV",
                    "https://www.telekom.de/sport/magenta-tv-fussball",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "DK": {
        "dau": 159_420,
        "langs": {
            "da": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "DRTV",
                    "https://www.dr.dk/drtv/kategorier/sport",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "TV 2 Play",
                    "https://play.tv2.dk/sport",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "EC": {
        "dau": 343_907,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Teleamazonas",
                    "https://www.teleamazonas.com/teleamazonas-en-vivo/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/ec/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "ES": {
        "dau": 1_165_642,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "RTVE",
                    "https://www.rtve.es/play/videos/copa-mundial-de-la-fifa-2026/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DAZN",
                    "https://www.dazn.com/es-ES/",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "FI": {
        "dau": 331_156,
        "langs": {
            "fi": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Yle Areena",
                    "https://areena.yle.fi/1-72511886",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "MTV Katsomo",
                    "https://www.mtv.fi/ohjelmat/fifa-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "FR": {
        "dau": 3_446_170,
        "langs": {
            "fr": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "M6+",
                    "https://www.m6.fr/coupe-du-monde-2026-p_26649",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "beIN SPORTS",
                    "https://connect.beinsports.com/france/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "GB": {
        "dau": 1_099_025,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "BBC iPlayer",
                    "https://www.bbc.co.uk/iplayer/episodes/m002gjj0/fifa-world-cup-2026",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "ITVX",
                    "https://www.itv.com/watch",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "STV Player",
                    "https://player.stv.tv/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "HU": {
        "dau": 397_461,
        "langs": {
            "hu": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "M4sport",
                    "https://m4sport.hu/elo/mtv4live/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "MÉDIAKLIKK",
                    "https://mediaklikk.hu/elo/dunalive/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "ID": {
        "dau": 1_547_076,
        "langs": {
            "id": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TVRI Klik",
                    "https://klik.tvri.go.id/detailchannel/TVRI_CH_03",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "IE": {
        "dau": 93_558,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "RTÉ Player",
                    "https://www.rte.ie/player/onnow",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "IT": {
        "dau": 1_347_066,
        "langs": {
            "it": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "RaiPlay",
                    "https://www.raiplay.it/programmi/mondialidicalcio2026",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DAZN",
                    "https://www.dazn.com/it-IT/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "MX": {
        "dau": 767_251,
        "langs": {
            "es": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Azteca Deportes",
                    "https://envivo.tvazteca.com/",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "ViX",
                    "https://vix.com/es-es/canales",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "NL": {
        "dau": 583_396,
        "langs": {
            "nl": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "NPO",
                    "https://npo.nl/start/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "NOS",
                    "https://nos.nl/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "NO": {
        "dau": 139_189,
        "langs": {
            "nn": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "NRK TV",
                    "https://tv.nrk.no/serie/fifa-fotball-vm-2026",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "TV 2 Play",
                    "https://www.tv2.no/livesport/fotball/turneringer/fifa-fotball-vm/a315b842-f4bc-5687-9ecb-3e06d6acdf9a/oversikt",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "NZ": {
        "dau": 120_875,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TVNZ+",
                    "https://www.tvnz.co.nz/competition/fifa-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "PL": {
        "dau": 2_083_429,
        "langs": {
            "pl": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TVP SPORT",
                    "https://sport.tvp.pl/transmisje",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "PT": {
        "dau": 221_862,
        "langs": {
            "pt": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "LiveModeTV - YouTube",
                    "https://www.youtube.com/@LiveModeTV_PT",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "sport tv",
                    "https://www.sporttv.pt/mundial-fifa-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "RO": {
        "dau": 240_836,
        "langs": {
            "ro": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "AntenaPLAY",
                    "https://antenaplay.ro/fifa-world-cup",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "RS": {
        "dau": 155_082,
        "langs": {
            "sr": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "RTS Planeta",
                    "https://rtsplaneta.rs/live/tv",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Arena Cloud",
                    "https://webtv.arenacloudtv.com/",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "SE": {
        "dau": 288_922,
        "langs": {
            "sv": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "TV4 Play",
                    "https://www.tv4play.se/kategorier/fifa-fotbolls-vm-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "SVT Play",
                    "https://www.svtplay.se/fifa-fotbolls-vm-2026",
                    3,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "SK": {
        "dau": 185_113,
        "langs": {
            "sk": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "JOJPLAY",
                    "https://play.joj.sk/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "US": {
        "dau": 7_434_829,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "Tubi",
                    "https://tubitv.com/hubs/fifa-world-cup-fox-hub",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "YouTube TV",
                    "https://tv.youtube.com/browse/UCgL1z0K3r-CJig5sXlSvDbg",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "FOX ONE",
                    "https://www.fox.com/soccer/fifa-world-cup",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DirecTV",
                    "https://www.directv.com/sports-info/soccer/worldcup",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Hulu",
                    "https://www.hulu.com/soccer",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Fubo",
                    "https://www.fubo.tv/stream/worldcup/",
                    4,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "Peacock",
                    "https://www.peacocktv.com/es-us/sports/copa-mundial#ib-section-section-6",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
    "ZA": {
        "dau": 196_702,
        "langs": {
            "en": [
                _build_fifa_watch_link(),
                build_watch_link(
                    "SABC+",
                    "https://sabc-plus.com/live",
                    2,
                    in_production=True,
                    show_in_other_regions=True,
                ),
                build_watch_link(
                    "DStv Stream",
                    "https://dstv.stream/#/",
                    5,
                    in_production=True,
                    show_in_other_regions=True,
                ),
            ],
        },
    },
}


COUNTRY_DISPLAY_CODES: dict[str, str] = {
    "AR": "ARG",
    "AT": "AUT",
    "AU": "AUS",
    "BE": "BEL",
    "BG": "BUL",
    "BR": "BRA",
    "CA": "CAN",
    "CH": "SUI",
    "CL": "CHI",
    "CO": "COL",
    "CZ": "CZE",
    "DE": "GER",
    "DK": "DEN",
    "EC": "ECU",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "GB": "UK",
    "HU": "HUN",
    "ID": "INA",
    "IE": "IRL",
    "IT": "ITA",
    "MX": "MEX",
    "NL": "NED",
    "NO": "NOR",
    "NZ": "NZL",
    "PL": "POL",
    "PT": "POR",
    "RO": "ROU",
    "RS": "SRB",
    "SE": "SWE",
    "SK": "SVK",
    "US": "USA",
    "ZA": "RSA",
}
