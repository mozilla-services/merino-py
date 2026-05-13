"""Static watch link mapping keyed by ISO country code and language prefix."""

from pydantic import HttpUrl

from merino.middleware.geolocation import Location

# Outer key: ISO 3166-1 alpha-2 country code (from geolocation middleware).
# Inner key: BCP 47 language prefix, e.g. "en", "de", "fr".
# The country already disambiguates the region, so the prefix is always unique
# within a country's entry. Multi-language countries (CH, BE) carry one entry
# per language.
WATCH_LINKS: dict[str, dict[str, list[str]]] = {
    "AR": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.tvpublica.com.ar/",
            "https://pluto.tv/latam/live-tv/66997d18a1b69e00082ee85f?lang=en",
            "https://www.paramountplus.com/ar/",
        ],
    },
    "AT": {
        "de": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://on.orf.at/live",
            "https://www.servustv.com/de/epg",
        ],
    },
    "AU": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.sbs.com.au/ondemand/watch/1726824003663",
        ],
    },
    "BE": {
        "fr": [
            "https://auvio.rtbf.be/categorie/football-11",
        ],
        "nl": [
            "https://www.vrt.be/vrtmax/kanalen/sporza/",
        ],
    },
    "BG": {
        "bg": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://tv.bnt.bg/",
        ],
    },
    "BR": {
        "pt": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.youtube.com/@CazeTV/streams",
            "https://mais.sbt.com.br/",
            "https://globoplay.globo.com/tv-globo/ao-vivo/6120663/",
        ],
    },
    "CA": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.tsn.ca/soccer/fifa-world-cup/",
            "https://www.rds.ca/soccer/coupe-du-monde/",
            "https://www.crave.ca/en/ctv",
        ],
    },
    "CH": {
        "de": [
            "https://www.srf.ch/play/tv/sport-livestreams",
        ],
        "fr": [
            "https://www.rts.ch/play/tv/rts-livestreams",
        ],
        "it": [
            "https://www.rsi.ch/play/tv/streaming",
        ],
    },
    "CL": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.chilevision.cl/senal-online/",
            "https://www.directvgo.com/cl/home",
            "https://www.paramountplus.com/cl/",
        ],
    },
    "CO": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.canalrcn.com/co/deportes",
            "https://ditu.caracoltv.com/category/copa-mundial-de-futbol-2026",
            "https://winplay.co/co/futbol-internacional",
            "https://www.directvla.com/co/mundial",
        ],
    },
    "CZ": {
        "cs": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://sport.ceskatelevize.cz/zive-vysilani",
            "https://tv.nova.cz/sledujte-zive/1-nova",
        ],
    },
    "DE": {
        "de": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.zdf.de/live-tv",
            "https://www.ardmediathek.de/live",
            "https://www.sportschau.de/fussball/fifa-wm-2026/",
            "https://www.telekom.de/sport/magenta-tv-fussball",
        ],
    },
    "DK": {
        "da": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.dr.dk/drtv/kategorier/sport",
            "https://play.tv2.dk/sport",
        ],
    },
    "EC": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.teleamazonas.com/teleamazonas-en-vivo/",
            "https://www.paramountplus.com/ec/",
        ],
    },
    "ES": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.rtve.es/play/videos/copa-mundial-de-la-fifa-2026/",
            "https://www.dazn.com/es-ES/",
        ],
    },
    "FI": {
        "fi": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://areena.yle.fi/1-72511886",
            "https://www.mtv.fi/ohjelmat/fifa-2026",
        ],
    },
    "FR": {
        "fr": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.m6.fr/coupe-du-monde-2026-p_26649",
            "https://connect.beinsports.com/france/",
        ],
    },
    "GB": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.bbc.co.uk/iplayer/episodes/m002gjj0/fifa-world-cup-2026",
            "https://www.itv.com/watch",
            "https://player.stv.tv/live",
        ],
    },
    "HU": {
        "hu": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://m4sport.hu/elo/mtv4live/",
            "https://mediaklikk.hu/elo/dunalive/",
        ],
    },
    "ID": {
        "id": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://klik.tvri.go.id/detailchannel/TVRI_CH_03",
        ],
    },
    "IE": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.rte.ie/player/onnow",
        ],
    },
    "IT": {
        "it": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.raiplay.it/programmi/mondialidicalcio2026",
            "https://www.dazn.com/it-IT/",
        ],
    },
    "MX": {
        "es": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://envivo.tvazteca.com/",
            "https://vix.com/es-es/canales",
        ],
    },
    "NL": {
        "nl": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://npo.nl/start/live",
            "https://nos.nl/live",
        ],
    },
    # TODO confirm if it's "nn" or "no"
    "NO": {
        "nn": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://tv.nrk.no/serie/fifa-fotball-vm-2026",
            "https://www.tv2.no/livesport/fotball/turneringer/fifa-fotball-vm/a315b842-f4bc-5687-9ecb-3e06d6acdf9a/oversikt",
        ],
    },
    "NZ": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.tvnz.co.nz/competition/fifa-2026",
        ],
    },
    "PL": {
        "pl": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://sport.tvp.pl/transmisje",
        ],
    },
    "PT": {
        "pt": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.youtube.com/@LiveModeTV_PT",
            "https://www.sporttv.pt/mundial-fifa-2026",
        ],
    },
    "RO": {
        "ro": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://antenaplay.ro/fifa-world-cup",
        ],
    },
    "RS": {
        "sr": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://rtsplaneta.rs/live/tv",
            "https://webtv.arenacloudtv.com/",
        ],
    },
    "SE": {
        "sv": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://www.tv4play.se/kategorier/fifa-fotbolls-vm-2026",
            "https://www.svtplay.se/fifa-fotbolls-vm-2026",
        ],
    },
    "SK": {
        "sk": [
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://play.joj.sk/",
        ],
    },
    "US": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://tubitv.com/hubs/fifa-world-cup-fox-hub",
            "https://tv.youtube.com/browse/UCgL1z0K3r-CJig5sXlSvDbg",
            "https://www.fox.com/soccer/fifa-world-cup",
            "https://www.directv.com/sports-info/soccer/worldcup",
            "https://www.hulu.com/soccer",
            "https://www.fubo.tv/stream/worldcup/",
            "https://www.peacocktv.com/es-us/sports/copa-mundial#ib-section-section-6",
        ],
    },
    "ZA": {
        "en": [
            "https://www.youtube.com/user/trevornoah",
            "https://www.plus.fifa.com/showcase/fifa-world-cup-26tm/89de0054-9fa6-4741-88e1-a902dc26740f",
            "https://sabc-plus.com/live",
            "https://dstv.stream/#/",
        ],
    },
}


def resolve_watch_links(
    geolocation: Location | None, accepted_languages: list[str]
) -> list[HttpUrl]:
    """Return watch links matched by country and highest-priority language prefix."""
    if geolocation is None or not geolocation.country:
        return []
    country_links = WATCH_LINKS.get(geolocation.country)
    if not country_links:
        return []
    for lang in accepted_languages:
        prefix = lang.split("-")[0]
        if prefix in country_links:
            return [HttpUrl(url) for url in country_links[prefix]]
    return []
