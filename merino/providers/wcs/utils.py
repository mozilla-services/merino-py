"""Utility helpers for the WCS provider."""

from merino.middleware.geolocation import Location
from merino.providers.wcs.team_colors import TEAM_COLOURS
from merino.providers.wcs.watch_links import WATCH_LINKS, WatchLinkEntry, COUNTRY_DISPLAY_CODES


def get_team_colours(team_key: str) -> list[str]:
    """Return the hex colour list for a team, or an empty list if not available."""
    return TEAM_COLOURS.get(team_key, [])


def _country_display_code(iso: str) -> str:
    """Return the display country code for an ISO 3166-1 alpha-2 code, falling back to the ISO code."""
    return COUNTRY_DISPLAY_CODES.get(iso, iso)


def _other_region_streams(candidates: list[WatchLinkEntry]) -> list[WatchLinkEntry]:
    """Return filtered, sorted streams for a country's other-regions section.

    Filters to in_production=True and show_in_other_regions=True, then sorts
    by product_name ascending, then sort_order ascending.
    """
    return sorted(
        (e for e in candidates if e.in_production and e.show_in_other_regions),
        key=lambda e: (e.product_name, e.sort_order),
    )


def resolve_watch_links(
    geolocation: Location | None, accepted_languages: list[str]
) -> list[WatchLinkEntry]:
    """Return in-production watch links matched by country and highest-priority language prefix.

    Language-specific entries are merged with country-wide ('*') entries, filtered to
    in_production=True, and sorted by sort_order then product_name ascending.

    # YOUR REGION
    # Filter: Show in production = 1
    # Filter: LOCAL COUNTRY EXACT MATCH
    # Sort:   Stream offer entitlement sort order A-Z (1=FIFA+, 2=Free, 3=Free and Paid, 4=Free Trial, 5=Paid)
    # Sort:   Stream product name A-Z
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
    geolocation: Location | None,
) -> list[tuple[str, list[WatchLinkEntry]]]:
    """Return (display_country_code, streams) for regions other than the user's.

    All non-user countries are included if they have at least one stream with
    in_production=True and show_in_other_regions=True. Countries are sorted by display
    code A-Z; streams within each country are sorted by product_name then sort_order.

    # OTHER REGIONS
    # Filter: Show in production = 1
    # Filter: LOCAL COUNTRY NON-MATCH
    # Filter: Show in other regions list = 1
    # Sort:   Country A-Z
    # Sort:   Stream product name A-Z
    # Sort:   Stream offer entitlement sort order A-Z
    """
    if geolocation is None or not geolocation.country:
        return []
    user_country = geolocation.country

    results: list[tuple[str, list[WatchLinkEntry]]] = []
    for iso, country_data in WATCH_LINKS.items():
        if iso == user_country:
            continue  # exclude the user's own country
        all_streams = [s for streams in country_data["langs"].values() for s in streams]
        streams = _other_region_streams(all_streams)
        if not streams:
            continue  # no qualifying streams for this country
        results.append((iso, streams))

    results.sort(key=lambda x: _country_display_code(x[0]))  # country A-Z
    return [(_country_display_code(iso), streams) for iso, streams in results]
