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
    "Amealco": "Amealco de Bonfil",
    "Aizu-wakamatsu Shi": "Aizu-wakamatsu",
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
    "Délı̨ne": "Deline",
    "Điện Bàn": "Dien Ban",
    "Dokki": "Giza",
    "Dombivali": "Dombivli",
    "Đông Hà": "Dong Ha",
    "Đồng Nại": "Dong Nai",
    "Ejido Culiacán (Culiacancito)": "Ejido Culiacán",
    "Ecatepec": "Ecatepec de Morelos",
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
    "Madīnat an Naşr": "Nasr",
    "Magnesia ad Sipylum": "Manisa",
    "Magdalena Contreras": "La Magdalena Contreras",
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

# Countries that use the most specific region to retrieve weather
KNOWN_SPECIFIC_REGION_COUNTRIES: frozenset = frozenset(
    ["AR", "AU", "BR", "CA", "CN", "DE", "FR", "GB", "MX", "NZ", "PL", "PT", "RU", "US"]
)
# Countries that use the least specific region to retrieve weather
KNOWN_REGION_COUNTRIES: frozenset = frozenset(["IT", "ES", "GR"])


def normalize_string(input_str: str) -> str:
    """Normalize string with special chcarcters"""
    return unicodedata.normalize("NFKD", input_str).encode("ascii", "ignore").decode("ascii")


def remove_locality_suffix(city: str) -> str:
    """Remove either city or municipality suffix from a city name"""
    return LOCALITY_SUFFIX_PATTERN.sub("", city)


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
