"""Static watch link mapping keyed by ISO country code and language prefix."""

from typing import TypedDict

from pydantic import BaseModel, Field, HttpUrl

from merino.middleware.geolocation import Location


_SORT_ORDER_LABELS: dict[int, str] = {
    0: "Trevor",
    1: "FIFA+",
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
        description="Display sort order: 0=Trevor, 1=FIFA, 2=Free, 3=Free and Paid, 4=Free Trial, 5=Paid."
    )
    in_production: bool = Field(description="True when this stream is enabled in production.")
    vpn_available: bool = Field(
        description="True when Firefox VPN is available in this stream's geo-location."
    )
    show_vpn_regions: bool = Field(
        description="True when this stream appears in the VPN-enabled regions list."
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
_TREVOR_NOAH_WATCH_PARTY = HttpUrl("https://www.youtube.com/user/trevornoah")


def _build_watch_link(
    product_name: str,
    url: str,
    sort_order: int,
    *,
    in_production: bool,
    vpn_available: bool,
    show_vpn_regions: bool,
) -> WatchLinkEntry:
    """Build a WatchLinkEntry from positional and keyword fields."""
    return WatchLinkEntry(
        product_name=product_name,
        url=HttpUrl(url),
        sort_order=sort_order,
        in_production=in_production,
        vpn_available=vpn_available,
        show_vpn_regions=show_vpn_regions,
    )


def _build_fifa_watch_link(
    *, vpn_available: bool, show_vpn_regions: bool = False
) -> WatchLinkEntry:
    """Build a FIFA+ entry reusing the shared showcase URL."""
    return WatchLinkEntry(
        product_name="FIFA+",
        url=_FIFA_PLUS,
        sort_order=1,
        in_production=True,
        vpn_available=vpn_available,
        show_vpn_regions=show_vpn_regions,
    )


def _build_trevor_noah_watch_party_link(
    *, vpn_available: bool, sort_order: int = 0
) -> WatchLinkEntry:
    """Build a Trevor Noah Watch Party entry reusing the shared YouTube URL."""
    return WatchLinkEntry(
        product_name="Trevor Noah's World Cup Watch Party",
        url=_TREVOR_NOAH_WATCH_PARTY,
        sort_order=sort_order,
        in_production=True,
        vpn_available=vpn_available,
        show_vpn_regions=False,
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
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "TVP",
                    "https://www.tvpublica.com.ar/",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Pluto TV",
                    "https://pluto.tv/latam/live-tv/66997d18a1b69e00082ee85f?lang=en",
                    4,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/ar/",
                    5,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "AT": {
        "dau": 501_177,
        "langs": {
            "de": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "ORF",
                    "https://on.orf.at/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "ServusTV",
                    "https://www.servustv.com/de/epg",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "AU": {
        "dau": 593_227,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "SBS On Demand",
                    "https://www.sbs.com.au/ondemand/watch/1726824003663",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "BE": {
        "dau": 369_344,
        "langs": {
            "*": [
                _build_fifa_watch_link(vpn_available=True),
            ],
            "fr": [
                _build_watch_link(
                    "RTBF",
                    "https://auvio.rtbf.be/categorie/football-11",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
            "nl": [
                _build_watch_link(
                    "VRT 1",
                    "https://www.vrt.be/vrtmax/kanalen/sporza/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "BG": {
        "dau": 173_120,
        "langs": {
            "bg": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "BNT",
                    "https://tv.bnt.bg/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "BR": {
        "dau": 1_923_018,
        "langs": {
            "pt": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "CazéTV - YouTube",
                    "https://www.youtube.com/@CazeTV/streams",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "SBT",
                    "https://mais.sbt.com.br/",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Globoplay",
                    "https://globoplay.globo.com/tv-globo/ao-vivo/6120663/",
                    3,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "CA": {
        "dau": 1_160_538,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "TSN",
                    "https://www.tsn.ca/soccer/fifa-world-cup/",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "RDS",
                    "https://www.rds.ca/soccer/coupe-du-monde/",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Crave",
                    "https://www.crave.ca/en/ctv",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "CH": {
        "dau": 539_945,
        "langs": {
            "*": [
                _build_fifa_watch_link(vpn_available=False),
            ],
            "de": [
                _build_watch_link(
                    "SRF",
                    "https://www.srf.ch/play/tv/sport-livestreams",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
            "fr": [
                _build_watch_link(
                    "RTS",
                    "https://www.rts.ch/play/tv/rts-livestreams",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
            "it": [
                _build_watch_link(
                    "RSI",
                    "https://www.rsi.ch/play/tv/streaming",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "CL": {
        "dau": 189_362,
        "langs": {
            "es": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "Chilevision",
                    "https://www.chilevision.cl/senal-online/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "DGO",
                    "https://www.directvgo.com/cl/home",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/cl/",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "CO": {
        "dau": 329_562,
        "langs": {
            "es": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "Canal RCN",
                    "https://www.canalrcn.com/co/deportes",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Ditu",
                    "https://ditu.caracoltv.com/category/copa-mundial-de-futbol-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Win Play",
                    "https://winplay.co/co/futbol-internacional",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "DIRECTV",
                    "https://www.directvla.com/co/mundial",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "CZ": {
        "dau": 481_742,
        "langs": {
            "cs": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "iVysílání",
                    "https://sport.ceskatelevize.cz/zive-vysilani",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Nova Action",
                    "https://tv.nova.cz/sledujte-zive/1-nova",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "DE": {
        "dau": 5_475_312,
        "langs": {
            "de": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "ZDF",
                    "https://www.zdf.de/live-tv",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "ARD",
                    "https://www.ardmediathek.de/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "SPORTSCHAU",
                    "https://www.sportschau.de/fussball/fifa-wm-2026/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "MagentaTV",
                    "https://www.telekom.de/sport/magenta-tv-fussball",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "DK": {
        "dau": 159_420,
        "langs": {
            "da": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "DRTV",
                    "https://www.dr.dk/drtv/kategorier/sport",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "TV 2 Play",
                    "https://play.tv2.dk/sport",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "EC": {
        "dau": 343_907,
        "langs": {
            "es": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "Teleamazonas",
                    "https://www.teleamazonas.com/teleamazonas-en-vivo/",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Paramount+",
                    "https://www.paramountplus.com/ec/",
                    5,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "ES": {
        "dau": 1_165_642,
        "langs": {
            "es": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "RTVE",
                    "https://www.rtve.es/play/videos/copa-mundial-de-la-fifa-2026/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "DAZN",
                    "https://www.dazn.com/es-ES/",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "FI": {
        "dau": 331_156,
        "langs": {
            "fi": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "Yle Areena",
                    "https://areena.yle.fi/1-72511886",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "MTV Katsomo",
                    "https://www.mtv.fi/ohjelmat/fifa-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "FR": {
        "dau": 3_446_170,
        "langs": {
            "fr": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "M6+",
                    "https://www.m6.fr/coupe-du-monde-2026-p_26649",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "beIN SPORTS",
                    "https://connect.beinsports.com/france/",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "GB": {
        "dau": 1_099_025,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "BBC iPlayer",
                    "https://www.bbc.co.uk/iplayer/episodes/m002gjj0/fifa-world-cup-2026",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "ITVX",
                    "https://www.itv.com/watch",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "STV Player",
                    "https://player.stv.tv/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "HU": {
        "dau": 397_461,
        "langs": {
            "hu": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "M4sport",
                    "https://m4sport.hu/elo/mtv4live/",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "MÉDIAKLIKK",
                    "https://mediaklikk.hu/elo/dunalive/",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "ID": {
        "dau": 1_547_076,
        "langs": {
            "id": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "TVRI Klik",
                    "https://klik.tvri.go.id/detailchannel/TVRI_CH_03",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "IE": {
        "dau": 93_558,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "RTÉ Player",
                    "https://www.rte.ie/player/onnow",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "IT": {
        "dau": 1_347_066,
        "langs": {
            "it": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "RaiPlay",
                    "https://www.raiplay.it/programmi/mondialidicalcio2026",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "DAZN",
                    "https://www.dazn.com/it-IT/",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "MX": {
        "dau": 767_251,
        "langs": {
            "es": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "Azteca Deportes",
                    "https://envivo.tvazteca.com/",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "ViX",
                    "https://vix.com/es-es/canales",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "NL": {
        "dau": 583_396,
        "langs": {
            "nl": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "NPO",
                    "https://npo.nl/start/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "NOS",
                    "https://nos.nl/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "NO": {
        "dau": 139_189,
        "langs": {
            "nn": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "NRK TV",
                    "https://tv.nrk.no/serie/fifa-fotball-vm-2026",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "TV 2 Play",
                    "https://www.tv2.no/livesport/fotball/turneringer/fifa-fotball-vm/a315b842-f4bc-5687-9ecb-3e06d6acdf9a/oversikt",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "NZ": {
        "dau": 120_875,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "TVNZ+",
                    "https://www.tvnz.co.nz/competition/fifa-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "PL": {
        "dau": 2_083_429,
        "langs": {
            "pl": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "TVP SPORT",
                    "https://sport.tvp.pl/transmisje",
                    2,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "PT": {
        "dau": 221_862,
        "langs": {
            "pt": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "LiveModeTV - YouTube",
                    "https://www.youtube.com/@LiveModeTV_PT",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "sport tv",
                    "https://www.sporttv.pt/mundial-fifa-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "RO": {
        "dau": 240_836,
        "langs": {
            "ro": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "AntenaPLAY",
                    "https://antenaplay.ro/fifa-world-cup",
                    5,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "RS": {
        "dau": 155_082,
        "langs": {
            "sr": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "RTS Planeta",
                    "https://rtsplaneta.rs/live/tv",
                    3,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
                _build_watch_link(
                    "Arena Cloud",
                    "https://webtv.arenacloudtv.com/",
                    4,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "SE": {
        "dau": 288_922,
        "langs": {
            "sv": [
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "TV4 Play",
                    "https://www.tv4play.se/kategorier/fifa-fotbolls-vm-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "SVT Play",
                    "https://www.svtplay.se/fifa-fotbolls-vm-2026",
                    3,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
            ],
        },
    },
    "SK": {
        "dau": 185_113,
        "langs": {
            "sk": [
                _build_fifa_watch_link(vpn_available=False),
                _build_watch_link(
                    "JOJPLAY",
                    "https://play.joj.sk/",
                    5,
                    in_production=True,
                    vpn_available=False,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "US": {
        "dau": 7_434_829,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "Tubi",
                    "https://tubitv.com/hubs/fifa-world-cup-fox-hub",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "YouTube TV",
                    "https://tv.youtube.com/browse/UCgL1z0K3r-CJig5sXlSvDbg",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "FOX ONE",
                    "https://www.fox.com/soccer/fifa-world-cup",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "DirecTV",
                    "https://www.directv.com/sports-info/soccer/worldcup",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Hulu",
                    "https://www.hulu.com/soccer",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Fubo",
                    "https://www.fubo.tv/stream/worldcup/",
                    4,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "Peacock",
                    "https://www.peacocktv.com/es-us/sports/copa-mundial#ib-section-section-6",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
    "ZA": {
        "dau": 196_702,
        "langs": {
            "en": [
                _build_trevor_noah_watch_party_link(vpn_available=True),
                _build_fifa_watch_link(vpn_available=True),
                _build_watch_link(
                    "SABC+",
                    "https://sabc-plus.com/live",
                    2,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=True,
                ),
                _build_watch_link(
                    "DStv Stream",
                    "https://dstv.stream/#/",
                    5,
                    in_production=True,
                    vpn_available=True,
                    show_vpn_regions=False,
                ),
            ],
        },
    },
}


_COUNTRY_DISPLAY_CODES: dict[str, str] = {
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


def _country_display_code(iso: str) -> str:
    """Return the display country code for an ISO 3166-1 alpha-2 code, falling back to the ISO code."""
    return _COUNTRY_DISPLAY_CODES.get(iso, iso)


def _other_region_streams(
    langs: dict[str, list[WatchLinkEntry]], lang_key: str | None
) -> list[WatchLinkEntry]:
    """Return filtered, sorted streams for a country's other-regions section.

    When `lang_key` is given, only that key's streams plus wildcard ('*') streams are
    considered. When None, all streams across every language key are considered.
    Filters to in_production=True, vpn_available=True, show_vpn_regions=True.
    """
    if lang_key is not None:
        candidates = langs.get(lang_key, []) + langs.get("*", [])
    else:
        candidates = [stream for streams in langs.values() for stream in streams]
    return sorted(
        (e for e in candidates if e.in_production and e.vpn_available and e.show_vpn_regions),
        key=lambda e: (e.sort_order, e.product_name),
    )


def resolve_watch_links(
    geolocation: Location | None, accepted_languages: list[str]
) -> list[WatchLinkEntry]:
    """Return in-production watch links matched by country and highest-priority language prefix.

    Language-specific entries are merged with country-wide ('*') entries, filtered to
    in_production=True, and sorted by sort_order then product_name ascending.
    """
    if geolocation is None or not geolocation.country:
        return []
    country_data = WATCH_LINKS.get(geolocation.country)
    if not country_data:  # country not covered
        return []
    langs = country_data["langs"]
    wildcard = langs.get("*", [])  # country-wide streams that apply to all languages
    lang_entries: list[WatchLinkEntry] = []
    for lang in accepted_languages:
        prefix = lang.split("-")[0]  # e.g. "en" from "en-US"
        if prefix in langs:
            lang_entries = langs[prefix]
            break  # use highest-priority language match only
    combined = lang_entries + wildcard
    return sorted(
        (entry for entry in combined if entry.in_production),
        key=lambda entry: (entry.sort_order, entry.product_name),
    )


def resolve_other_regions(
    geolocation: Location | None, accepted_languages: list[str]
) -> list[tuple[str, list[WatchLinkEntry]]]:
    """Return (display_country_code, streams) for regions other than the user's.

    Returns lang-match countries first (sorted by matched lang prefix A-Z, then DAU
    descending), followed by no-lang-match countries (sorted by display code A-Z).
    Within each country, streams are sorted by sort_order then product_name ascending.
    Only streams with in_production=True, vpn_available=True, and show_vpn_regions=True
    are included.
    """
    if geolocation is None or not geolocation.country:
        return []
    user_country = geolocation.country
    user_lang_prefix = accepted_languages[0][:2] if accepted_languages else ""  # e.g. "en"

    lang_match: list[tuple[str, str, int, list[WatchLinkEntry]]] = []
    no_lang_match: list[tuple[str, int, list[WatchLinkEntry]]] = []

    for iso, country_data in WATCH_LINKS.items():
        if iso == user_country:
            continue  # exclude the user's own country

        langs = country_data["langs"]
        dau = country_data["dau"]

        matched_lang: str | None = None
        if user_lang_prefix:
            for lang_key in langs:
                if lang_key != "*" and lang_key[:2] == user_lang_prefix:
                    matched_lang = lang_key
                    break  # first matching lang key wins

        streams = _other_region_streams(langs, matched_lang)
        if not streams:
            continue  # no qualifying streams for this country

        if matched_lang:
            lang_match.append((matched_lang, iso, dau, streams))
        else:
            no_lang_match.append((iso, dau, streams))

    lang_match.sort(key=lambda x: (x[0], -x[2]))  # lang A-Z, then DAU descending
    no_lang_match.sort(key=lambda x: _country_display_code(x[0]))  # display code A-Z

    lang_match_result = [
        (_country_display_code(iso), streams) for _, iso, _, streams in lang_match
    ]
    no_lang_match_result = [
        (_country_display_code(iso), streams) for iso, _, streams in no_lang_match
    ]
    return lang_match_result + no_lang_match_result
