"""Pathfinder - a utility to reconcile geolocation distinctions between MaxmindDB and AccuWeather."""

from typing import Any, Awaitable, Callable, Generator, Optional

from merino.middleware.geolocation import Location


MaybeStr = Optional[str]
Triplet = tuple[MaybeStr, MaybeStr, MaybeStr]

SUCCESSFUL_REGIONS_MAPPING: dict[tuple[str, str], str | None] = {}


def compass(location: Location) -> Generator[Triplet, None, None]:
    """Generate all the "country, region, city" triplets based on a `Location`.

    It will generate ones that are more likely to produce a valid result based on heuristics.

    Params:
      - location {Location}: a location object.
    Returns:
      - A tuple of "country, region, city", with each element could be None.
    """
    # TODO(nanj): add more heuristics to here.

    # Append None as the fallback since AccuWeather can take params w/o the region code
    if (
        location.country
        and location.city
        and (location.country, location.city) in SUCCESSFUL_REGIONS_MAPPING
    ):
        regions = [SUCCESSFUL_REGIONS_MAPPING[(location.country, location.city)]]
    elif location.regions is not None:
        regions = [*location.regions, None]
    else:
        regions = [None]

    for region in regions:
        yield location.country, region, location.city


async def explore(
    location: Location, probe: Callable[[MaybeStr, MaybeStr, MaybeStr], Awaitable[Optional[Any]]]
) -> Optional[Any]:
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
    for country, region, city in compass(location):
        res = await probe(country, region, city)

        if res not in (None, []):
            if country and city:
                SUCCESSFUL_REGIONS_MAPPING[(country, city)] = region
            return res

    return None
