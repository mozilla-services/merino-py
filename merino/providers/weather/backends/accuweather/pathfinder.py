"""Pathfinder - a utility to reconcile geolocation distinctions between MaxmindDB and AccuWeather."""

from typing import Any, Awaitable, Callable, Generator, Optional

from merino.middleware.geolocation import Location

MaybeStr = Optional[str]
Triplet = tuple[MaybeStr, MaybeStr, MaybeStr]

SUCCESSFUL_REGIONS_MAPPING: dict[tuple[str, str], str | None] = {}
REGION_MAPPING_EXCLUSIONS: frozenset = frozenset(["CA", "ES", "GR", "IT", "US"])
CITY_NAME_CORRECTION_MAPPING: dict[str, str] = {
    "La'ie": "Laie",
    "Mitchell/Ontario": "Mitchell",
    "Montreal West": "Montreal",
    "Kleinburg Station": "Kleinburg",
    "Middlebury (village)": "Middlebury",
    "TracadieSheila": "Tracadie Sheila",
}
SKIP_CITIES_LIST: frozenset = frozenset(
    [
        ("CA", "AB", "Sturgeon County"),
        ("CA", "ON", "North Park"),
        ("US", "GA", "South Fulton"),
        ("US", "KY", "Fort Campbell North"),
        ("US", "TX", "Fort Cavazos"),
        ("US", "WA", "Joint Base Lewis McChord"),
    ]
)


def compass(location: Location) -> Generator[Triplet, None, None]:
    """Generate all the "country, region, city" triplets based on a `Location`.

    It will generate ones that are more likely to produce a valid result based on heuristics.

    Params:
      - location {Location}: a location object.
    Returns:
      - A tuple of "country, region, city", with each element could be None.
    """
    # TODO(nanj): add more heuristics to here.

    country = location.country
    regions = location.regions
    city = location.city

    if regions and country and city:
        city = CITY_NAME_CORRECTION_MAPPING.get(city, city)
        match (country, city):
            case ("US" | "CA", _):
                yield country, regions[0], city
                # use the most specific region
            case ("IT" | "ES" | "GR", _):
                yield (
                    country,
                    regions[-1],
                    city,
                )  # use the least specific region
            case (country, city) if (
                country,
                city,
            ) in SUCCESSFUL_REGIONS_MAPPING:  # dynamic rules we've learned
                yield country, SUCCESSFUL_REGIONS_MAPPING[(country, city)], city
            case _:  # Fall back to try all triplets
                regions_to_try = [*regions, None]
                for region in regions_to_try:
                    yield country, region, city
    else:
        yield country, None, city


async def explore(
    location: Location,
    probe: Callable[..., Awaitable[Optional[Any]]],
    language: str | None = None,
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
    for country, region, city in compass(location):
        if (country, region, city) in SKIP_CITIES_LIST:
            return None, True
        if language:
            res = await probe(country, region, city, language)
        else:
            res = await probe(country, region, city)
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
    if country not in REGION_MAPPING_EXCLUSIONS:
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
