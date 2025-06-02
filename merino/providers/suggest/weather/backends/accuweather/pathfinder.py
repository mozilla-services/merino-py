"""Pathfinder - a utility to reconcile geolocation distinctions between MaxmindDB and AccuWeather."""

import unicodedata
import re

from typing import Any, Awaitable, Callable, Generator, Optional

from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.protocol import WeatherContext

MaybeStr = Optional[str]

LOCALITY_SUFFIX_PATTERN: re.Pattern = re.compile(r"\s+(city|municipality|town)$", re.IGNORECASE)
SUCCESSFUL_REGIONS_MAPPING: dict[tuple[str, str], str | None] = {
    ("AR", "El Sombrero"): None,
    ("BR", "Barcellos"): None,
    ("GB", "London"): "LND",
    ("IE", "Dublin"): None,
    ("IN", "Angul"): None,
    ("IN", "Bhadrāchalam"): None,
    ("IN", "Hanamkonda"): None,
    ("IN", "Secunderabad"): None,
    ("IN", "Hyderabad"): None,
    ("MX", "Comalapa"): None,
    ("PH", "Manila"): None,
}

CITY_NAME_CORRECTION_MAPPING: dict[str, str] = {
    # 3 km away
    "Adrogué": "José Marmol",
    "Aizu-wakamatsu Shi": "Aizu-wakamatsu",
    "Altona": "Hamburg-Altona",
    "Amealco": "Amealco de Bonfil",
    # part of greater London
    "Archway": "London",
    "Baie Ste. Anne": "Baie-Sainte-Anne",
    "Banī Suwayf": "Beni Suef",
    "Barishal": "Barisal",
    "Belem": "Belém",
    "Białołeka": "Bialoleka",
    "Boca del Rio": "Boca del Río",
    # Bochum is a borough of Hordel
    "Bochum-Hordel": "Hordel",
    "Bogota D.C.": "Bogota",
    "Ciudad de Huajuapan de León": "Heroica Ciudad de Huajuapan de León",
    "Changwat Sara Buri": "Saraburi",
    "Chilpancingo": "Chilpancingo de los Bravo",
    "Chiyayi County": "Chiayi",
    "Derry": "Londonderry",
    "Délı̨ne": "Deline",
    "Điện Bàn": "Dien Ban",
    "Dokki": "Giza",
    "Dombivali": "Dombivli",
    "Đông Hà": "Dong Ha",
    "Đồng Nại": "Dong Nai",
    "Ecatepec": "Ecatepec de Morelos",
    "Ejido Culiacán (Culiacancito)": "Ejido Culiacán",
    "Ellesmere Port Town": "Ellesmere",
    "Faridpurāhāti": "Faridpur",
    "Fort Cavazos": "Killeen",
    "Gaibandha": "Gaibanda",
    "Gharroli": "Gharoli",
    "Grajales": "Rafael Lara Grajales",
    "Grand Bay–Westfield": "Grand Bay Westfield",
    "Guadalajara de Buga": "Buga",
    "Gustavo Adolfo Madero": "Gustavo A. Madero",
    "Hakusan'ura": "Hakusanura",
    "Hameln": "Hamelin",
    "Hannover": "Hanover",
    # district in Onomichi
    "Haradachō-obara": "Onomichi",
    "Huatulco": "Santa María Huatulco",
    # Santiago is a metropolitan city which contains Huechuraba
    "Huechuraba": "Santiago",
    "Izumi-honchō": "Izumihoncho",
    "Ixtapa-Zihuatanejo": "Zihuatanejo",
    "Ixtepec": "Ciudad Ixtepec",
    "Jalpan": "Jalpan de Serra",
    "Jīnd": "Jind",
    "Juchitán de Zaragoza": "Heroica Ciudad de Juchitán de Zaragoza",
    # 12 km away
    "Joint Base Lewis McChord": "Lakewood",
    "Kampungbaru": "Kampung Baru",
    "Kalasin": "Mueang Kalasin",
    "Kawachi-nagano Shi": "Kawachinagano-shi",
    "Kayapınar": "Kayapinar",
    "Kishorganj": "Kishoreganj",
    "Kleinburg Station": "Kleinburg",
    "Ko Pha Ngan": "Ko Pha-Ngan",
    "Kushi Nagar": "Kushinagar",
    "Lake Shasta": "Shasta Lake",
    "La'ie": "Laie",
    "Livramento do Brumado": "Livramento de Nossa Senhora",
    "Lyon 03": "Lyon",
    "Lyon 06": "Lyon",
    "Lyon 07": "Lyon",
    "Lyon 08": "Lyon",
    "Lyon 09": "Lyon",
    "Madīnat an Naşr": "Nasr",
    "Magnesia ad Sipylum": "Manisa",
    "Magdalena Contreras": "La Magdalena Contreras",
    # Neighbourhood in Paris
    "Maison Blanche": "Paris",
    "Marseille 08": "Marseille",
    "Marseille 09": "Marseille",
    "Marseille 10": "Marseille",
    "Marseille 11": "Marseille",
    "Marseille 12": "Marseille",
    "Marseille 13": "Marseille",
    "Marseille 14": "Marseille",
    "Marseille 15": "Marseille",
    "Matías Romero": "Matías Romero Avendaño",
    "Middlebury (village)": "Middlebury",
    "Mitchell/Ontario": "Mitchell",
    "Mixquiahuala de Juarez": "Mixquiahuala de Juárez",
    "Montreal East": "Montreal",
    "Montreal West": "Montreal",
    "Mossel Bay": "Mosselbaai",
    "Mīt Ghamr": "Mit Ghamr",
    "Mueang Pattani": "Pattani",
    "Municipality of Strathfield": "Strathfield",
    "Naucalpan": "Naucalpan de Juárez",
    "Nishi-Tokyo-shi": "Nishitokyo",
    # North Kuta is part of Badung
    "North Kuta": "Badung",
    "Ōkubo-naka": "Okubo naka",
    "Oaxaca City": "Oaxaca de Juárez",
    # Odunpazari is an area within the city Eskişehir
    "Odunpazari": "Eskişehir",
    "Pachuca": "Pachuca de Soto",
    "Panderma": "Bandırma",
    "Panjim": "Panaji",
    "Parigi Kulon": "Parigi",
    "Paris 10e Arrondissement": "Paris",
    "Paris 11e Arrondissement": "Paris",
    "Paris 12e Arrondissement": "Paris",
    "Paris 13e Arrondissement": "Paris",
    "Pasig-bo": "Lambunao",
    "Pilāni": "Pilani",
    "Port Montt": "Puerto Montt",
    "Province of Pangasinan": "Pangasinan",
    "Puerto Juárez": "Benito Juárez",
    # 3km away
    "Quweisna": "Quwaysna",
    "Quận Bình Thạnh": "Bình Thạnh",
    "Rahim Yar Khan": "Rahimyar Khan",
    # 13 km away
    "Research Triangle Park": "Durham",
    "Rüsselsheim am Main": "Rüsselsheim",
    "Ste. Anne de la Pocatière": "Sainte-Anne-de-la-Pocatière",
    "Sainte-Clotilde-de-Châteauguay": "Sainte-Clotilde-de-Chateauguay",
    "Sainte-Geneviève": "Sainte-Genevieve",
    "Saint-Barnabe": "Saint-Barnabé",
    "Saint Peters": "St Peter's",
    "Saint-Raymond-de-Portneuf": "Saint-Raymond",
    "Santa María Chimalhuacán": "Chimalhuacán",
    "Santiago de Cali": "Cali",
    "Santiago Metropolitan": "Santiago",
    "San Pedro One": "San Pedro I",
    "Selat Panjang": "Selatpanjang",
    "Shikoku-chūō Shi": "Shikokuchuo",
    "Silao": "Silao de la Victoria",
    "Skudai": "Sekudai",
    "Sōsa": "Sosa-shi",
    # Mueang Sukhothai encompasses Sukhothai Thani
    "Sukhothai Thani": "Mueang Sukhothai",
    "Thành phố Trà Vinh": "Trà Vinh",
    # Timika is part Mimika
    "Timika": "Mimika",
    "Toukh": "Tukh",
    "Tokat Province": "Tokat",
    "Tracadie–Sheila": "Tracadie Sheila",
    "Vatakara": "Vadakara",
    "Vitoria": "Vitória da Conquista",
    "Yunderup": "South Yunderup",
    "Zacoalco": "Zacoalco de Torres",
    "Zimapan": "Zimapán",
}

SKIP_CITIES_MAPPING: dict[tuple[str, str | None, str], int] = {
    ("CA", "AB", "Sturgeon County"): 0,
    ("CA", "ON", "North Park"): 0,
    ("CA", "ON", "Ontario"): 0,
    ("US", "AL", "Fort Novosel"): 0,
    ("US", "GA", "South Fulton"): 0,
    ("US", "KY", "Fort Campbell North"): 0,
    ("US", "ND", "Minot Air Force Base"): 0,
    ("US", "TX", "Fort Cavazos"): 0,
    ("US", "TX", "Lavaca"): 0,
    ("US", "UT", "Hill Air Force Base"): 0,
}

# mapping from https://dev.maxmind.com/geoip/whats-new-in-geoip2/#iso-3166-2-fips-10-4-and-country-subdivisions
# FR not included since the mapping does not map to ISO codes.
FIPS_ISO_MAPPING = {
    "CA": {
        "01": "AB",
        "02": "BC",
        "03": "MB",
        "04": "NB",
        "05": "NL",
        "07": "NS",
        "08": "ON",
        "09": "PE",
        "10": "QC",
        "11": "SK",
        "12": "YT",
        "13": "NT",
        "14": "NU",
    },
    "DE": {
        "01": "BW",
        "10": "SH",
        "11": "BB",
        "12": "MV",
        "13": "SN",
        "14": "ST",
        "15": "TH",
        "16": "BE",
        "02": "BY",
        "03": "HB",
        "04": "HH",
        "05": "HE",
        "06": "NI",
        "07": "NW",
        "08": "RP",
        "09": "SL",
    },
    "GB": {
        "1A": "ANN",
        "1B": "NMD",
        "2A": "AND",
        "3A": "ABC",
        "4A": "CCG",
        "5A": "DRS",
        "6A": "FMO",
        "7A": "LBC",
        "8A": "MEA",
        "9A": "MUL",
        "A1": "BDG",
        "A2": "BNE",
        "A3": "BNS",
        "A4": "BAS",
        "A5": "BDF",
        "A6": "BEX",
        "A7": "BIR",
        "A8": "BBD",
        "A9": "BPL",
        "B1": "BOL",
        "B2": "BMH",
        "B3": "BRC",
        "B4": "BRD",
        "B5": "BEN",
        "B6": "BNH",
        "B7": "BST",
        "B8": "BRY",
        "B9": "BKM",
        "C1": "BUR",
        "C2": "CLD",
        "C3": "CAM",
        "C4": "CMD",
        "C5": "CHS",
        "C6": "CON",
        "C7": "COV",
        "C8": "CRY",
        "C9": "CMA",
        "D1": "DAL",
        "D2": "DER",
        "D3": "DBY",
        "D4": "DEV",
        "D5": "DNC",
        "D6": "DOR",
        "D7": "DUD",
        "D8": "DUR",
        "D9": "EAL",
        "E1": "ERY",
        "E2": "ESX",
        "E3": "ENF",
        "E4": "ESS",
        "E5": "GAT",
        "E6": "GLS",
        "E7": "GRE",
        "E8": "HCK",
        "E9": "HAL",
        "F1": "HMF",
        "F2": "HAM",
        "F3": "HRY",
        "F4": "HRW",
        "F5": "HPL",
        "F6": "HAV",
        "F7": "HEF",
        "F8": "HRT",
        "F9": "HIL",
        "G1": "HNS",
        "G2": "IOW",
        "G3": "ISL",
        "G4": "KEC",
        "G5": "KEN",
        "G6": "KHL",
        "G7": "KTT",
        "G8": "KIR",
        "G9": "KWL",
        "H1": "LBH",
        "H2": "LAN",
        "H3": "LDS",
        "H4": "LCE",
        "H5": "LEC",
        "H6": "LEW",
        "H7": "LIN",
        "H8": "LIV",
        "H9": "LND",
        "I1": "LUT",
        "I2": "MAN",
        "I3": "MDW",
        "I4": "MRT",
        "I5": "MDB",
        "I6": "MIK",
        "I7": "NET",
        "I8": "NWM",
        "I9": "NFK",
        "J1": "NTH",
        "J2": "NEL",
        "J3": "NLN",
        "J4": "NSM",
        "J5": "NTY",
        "J6": "NBL",
        "J7": "NYK",
        "J8": "NGM",
        "J9": "NTT",
        "K1": "OLD",
        "K2": "OXF",
        "K3": "PTE",
        "K4": "PLY",
        "K5": "POL",
        "K6": "POR",
        "K7": "RDG",
        "K8": "RDB",
        "K9": "RCC",
        "L1": "RIC",
        "L2": "RCH",
        "L3": "ROT",
        "L4": "RUT",
        "L5": "SLF",
        "L6": "SHR",
        "L7": "SAW",
        "L8": "SFT",
        "L9": "SHF",
        "M1": "SLG",
        "M2": "SOL",
        "M3": "SOM",
        "M4": "STH",
        "M5": "SOS",
        "M6": "SGC",
        "M7": "STY",
        "M8": "SWK",
        "M9": "STS",
        "N1": "SHN",
        "N2": "SKP",
        "N3": "STT",
        "N4": "STE",
        "N5": "SFK",
        "N6": "SND",
        "N7": "SRY",
        "N8": "STN",
        "N9": "SWD",
        "O1": "TAM",
        "O2": "TFW",
        "O3": "THR",
        "O4": "TOB",
        "O5": "TWH",
        "O6": "TRF",
        "O7": "WKF",
        "O8": "WLL",
        "O9": "WFT",
        "P1": "WND",
        "P2": "WRT",
        "P3": "WAR",
        "P4": "WBK",
        "P5": "WSM",
        "P6": "WSX",
        "P7": "WGN",
        "P8": "WIL",
        "P9": "WNM",
        "Q1": "WRL",
        "Q2": "WOK",
        "Q3": "WLV",
        "Q4": "WOR",
        "Q5": "YOR",
        "Q6": "ANT",
        "Q7": "ARD",
        "Q8": "ARM",
        "Q9": "BLA",
        "R1": "BLY",
        "R2": "BNB",
        "R3": "BFS",
        "R4": "CKF",
        "R5": "CSR",
        "R6": "CLR",
        "R7": "CKT",
        "R8": "CGV",
        "R9": "DOW",
        "S1": "DGN",
        "S2": "FER",
        "S3": "LRN",
        "S4": "LMV",
        "S5": "LSB",
        "S6": "DRY",
        "S7": "MFT",
        "S8": "MYL",
        "S9": "NYM",
        "T1": "NTA",
        "T2": "NDN",
        "T3": "OMH",
        "T4": "STB",
        "T5": "ABE",
        "T6": "ABD",
        "T7": "ANS",
        "T8": "AGB",
        "T9": "SCB",
        "U1": "CLK",
        "U2": "DGY",
        "U3": "DND",
        "U4": "EAY",
        "U5": "EDU",
        "U6": "ELN",
        "U7": "ERW",
        "U8": "EDH",
        "U9": "FAL",
        "V1": "FIF",
        "V2": "GLG",
        "V3": "HLD",
        "V4": "IVC",
        "V5": "MLN",
        "V6": "MRY",
        "V7": "NAY",
        "V8": "NLK",
        "V9": "ORK",
        "W1": "PKN",
        "W2": "RFW",
        "W3": "ZET",
        "W4": "SAY",
        "W5": "SLK",
        "W6": "STG",
        "W7": "WDU",
        "W8": "ELS",
        "W9": "WLN",
        "X1": "AGY",
        "X2": "BGW",
        "X3": "BGE",
        "X4": "CAY",
        "X5": "CRF",
        "X6": "CGN",
        "X7": "CMN",
        "X8": "CWY",
        "X9": "DEN",
        "Y1": "FLN",
        "Y2": "GWN",
        "Y3": "MTY",
        "Y4": "MON",
        "Y5": "NTL",
        "Y6": "NWP",
        "Y7": "PEM",
        "Y8": "POW",
        "Y9": "RCT",
        "Z1": "SWA",
        "Z2": "TOF",
        "Z3": "VGL",
        "Z4": "WRX",
        "Z5": "BDF",
        "Z6": "CBF",
        "Z7": "CHE",
        "Z8": "CHW",
        "Z9": "IOS",
    },
    "IT": {
        "01": "65",
        "10": "57",
        "11": "67",
        "12": "21",
        "13": "75",
        "14": "88",
        "15": "82",
        "16": "52",
        "17": "32",
        "18": "55",
        "19": "23",
        "02": "77",
        "20": "34",
        "03": "78",
        "04": "72",
        "05": "45",
        "06": "36",
        "07": "62",
        "08": "42",
        "09": "25",
    },
    "PL": {
        "72": "02",
        "73": "04",
        "74": "10",
        "75": "06",
        "76": "08",
        "77": "12",
        "78": "14",
        "79": "16",
        "80": "18",
        "81": "20",
        "82": "22",
        "83": "24",
        "84": "26",
        "85": "28",
        "86": "30",
        "87": "32",
    },
}

FIPS_ISO_MAPPING_COUNTRIES: frozenset = frozenset(FIPS_ISO_MAPPING.keys())

# Countries that use the most specific region to retrieve weather
KNOWN_SPECIFIC_REGION_COUNTRIES: frozenset = frozenset(
    ["AR", "AU", "BR", "CA", "CN", "DE", "GB", "MX", "NZ", "PL", "PT", "RU", "US"]
)
# Countries that use the least specific region to retrieve weather
KNOWN_REGION_COUNTRIES: frozenset = frozenset(["IT", "ES", "GR"])


def normalize_string(input_str: str) -> str:
    """Normalize string with special chcarcters"""
    return unicodedata.normalize("NFKD", input_str).encode("ascii", "ignore").decode("ascii")


def remove_locality_suffix(city: str) -> str:
    """Remove either city or municipality suffix from a city name"""
    return LOCALITY_SUFFIX_PATTERN.sub("", city)


def get_fips_region_mapping(country: str, regions: list[str]) -> list[str]:
    """Get iso code for region if it exists in mapping."""
    for region in regions:
        if iso_region := FIPS_ISO_MAPPING.get(country, {}).get(region):
            return [iso_region]
    return regions


CITY_NAME_NORMALIZERS: list[Callable[[str], str]] = [
    lambda a: a,
    normalize_string,
    remove_locality_suffix,
]


def compass(location: Location) -> Generator[MaybeStr, None, None]:
    """Generate all the regions based on a `Location`.

    It will generate ones that are more likely to produce a valid result based on heuristics.

    Params:
      - location {Location}: a location object.
    Returns:
      - region string that could be None.
    """
    country = location.country
    regions = location.regions
    if country and country in FIPS_ISO_MAPPING_COUNTRIES and regions:
        regions = get_fips_region_mapping(country, regions)

    city = location.city

    if regions and country and city:
        match (country, city):
            case (country, city) if (
                country,
                city,
            ) in SUCCESSFUL_REGIONS_MAPPING:  # dynamic rules we've learned
                yield SUCCESSFUL_REGIONS_MAPPING[(country, city)]
            case (country_code, _) if country_code in KNOWN_SPECIFIC_REGION_COUNTRIES:
                # use the most specific region
                yield regions[0]
            case (country_code, _) if country_code in KNOWN_REGION_COUNTRIES:
                yield regions[-1]  # use the least specific region
            case _:  # Fall back to try all regions
                regions_to_try = [*regions, None]
                for region in regions_to_try:
                    yield region
    else:
        yield None


async def explore(
    weather_context: WeatherContext,
    probe: Callable[..., Awaitable[Optional[Any]]],
) -> tuple[Optional[Any], bool]:
    """Repeatedly executes an async function (prober) for each candidate until a valid result (path) is found.

    This can be used to find a result from various sources (cache or upstream API) for all possible location combinations.

    Note: The pathfinding will abort upon prober exceptions. It's up to the caller to handle exceptions
    raised from the prober.

    Params:
      - location {Location}: a location object.
      - probe {Callable}: an async function that takes a "country, region, city" triplet and resolves
        to `Optional[Any]`. Any non-None value will be treated as a successful probe, which will end
        the pathfinding and be returned.
    Returns:
      - The first non-None value returned by `probe`.
    Raises:
      - Any exception raised from `probe`.
    """
    is_skipped = False
    geolocation = weather_context.geolocation
    country = geolocation.country

    if geolocation.city is None:
        return None, is_skipped

    city = CITY_NAME_CORRECTION_MAPPING.get(geolocation.city, geolocation.city)
    # map is lazy, so items of `cities` would only be evaluated one by one if needed
    cities = map(lambda fn: fn(city), CITY_NAME_NORMALIZERS)
    # store the explored cities to avoid duplicates
    explored_cities: list[str] = []
    for city in cities:
        if city in explored_cities:
            continue
        explored_cities.append(city)
        for region in compass(weather_context.geolocation):
            if country and city and (country, region, city) in SKIP_CITIES_MAPPING:
                # increment since we tried to look up this combo again.
                increment_skip_cities_mapping(country, region, city)
                return None, True

            weather_context.selected_region = region
            weather_context.selected_city = city
            res = await probe(weather_context)

            if res is not None:
                return res, is_skipped

    return None, is_skipped


def set_region_mapping(country: str, city: str, region: str | None):
    """Set country, city, region into SUCCESSFUL_REGIONS_MAPPING
    that don't fall in countries where region can be determined.

    Params:
      - country {str}: country code
      - city {str}: city name
      - region {str | None}: region code
    """
    if country not in KNOWN_REGION_COUNTRIES and country not in KNOWN_SPECIFIC_REGION_COUNTRIES:
        SUCCESSFUL_REGIONS_MAPPING[(country, city)] = region


def get_region_mapping() -> dict[tuple[str, str], str | None]:
    """Get SUCCESSFUL_REGIONS_MAPPING."""
    return SUCCESSFUL_REGIONS_MAPPING


def get_region_mapping_size() -> int:
    """Get SUCCESSFUL_REGIONS_MAPPING size."""
    return len(SUCCESSFUL_REGIONS_MAPPING)


def clear_region_mapping() -> None:
    """Clear SUCCESSFUL_REGIONS_MAPPING."""
    SUCCESSFUL_REGIONS_MAPPING.clear()


def increment_skip_cities_mapping(country: str, region: str | None, city: str) -> None:
    """Increment the value of the (country, region, city) key or add it if not present.

    Params:
      - country {str}: country code
      - region {str | None}: region code
      - city {str}: city name

    """
    location = (country, region, city)
    if location in SKIP_CITIES_MAPPING:
        SKIP_CITIES_MAPPING[location] += 1
    else:
        SKIP_CITIES_MAPPING[location] = 1


def get_skip_cities_mapping() -> dict[tuple[str, str | None, str], int]:
    """Get SKIP_CITIES_MAPPING."""
    return SKIP_CITIES_MAPPING


def get_skip_cities_mapping_size() -> int:
    """Get SKIP_CITIES_MAPPING size."""
    return len(SKIP_CITIES_MAPPING)


def get_skip_cities_mapping_total() -> int:
    """Get the sum of the values of SKIP_CITIES_MAPPING"""
    return sum(SKIP_CITIES_MAPPING.values())


def clear_skip_cities_mapping() -> None:
    """Clear SKIP_CITIES_MAPPING."""
    SKIP_CITIES_MAPPING.clear()
