"""Utility helpers for the WCS provider."""

from merino.middleware.geolocation import Location
from merino.providers.wcs.team_colors import TEAM_COLOURS
from merino.providers.wcs.watch_links import (
    COUNTRY_DISPLAY_CODES,
    WATCH_LINKS,
    CountryEntry,
    WatchLinkEntry,
)


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


def _find_lang_streams(
    langs: dict[str, list[WatchLinkEntry]], accepted_languages: list[str]
) -> list[WatchLinkEntry]:
    """Return streams for the highest-priority matching language prefix.

    BCP-47 tags are matched by prefix only ("en-US" matches key "en"). Returns []
    if no accepted language has a matching key.
    """
    for lang in accepted_languages:
        prefix = lang.split("-")[0]
        if prefix in langs:
            return langs[prefix]
    return []


def _flatten_country_streams(country_data: CountryEntry) -> list[WatchLinkEntry]:
    """Return all streams for a country, pooled across every language key."""
    return [stream for lang_streams in country_data["langs"].values() for stream in lang_streams]


def resolve_watch_links(
    geolocation: Location | None, accepted_languages: list[str]
) -> list[WatchLinkEntry]:
    """Return in-production watch links for the user's country and language.

    Language-specific streams are merged with country-wide ('*') streams,
    filtered to in_production=True, and sorted by sort_order ascending then
    product_name ascending.
    """
    if geolocation is None or not geolocation.country:
        return []

    country_data = WATCH_LINKS.get(geolocation.country)
    if country_data is None:
        return []

    langs = country_data["langs"]
    country_wide_streams = langs.get("*", [])
    lang_streams = _find_lang_streams(langs, accepted_languages)
    candidates = lang_streams + country_wide_streams

    return sorted(
        (entry for entry in candidates if entry.in_production),
        key=lambda entry: (entry.sort_order, entry.product_name),
    )


def resolve_other_regions(
    geolocation: Location | None,
) -> list[tuple[str, list[WatchLinkEntry]]]:
    """Return (display_country_code, streams) for all regions other than the user's.

    Only countries with at least one stream passing the in_production and
    show_in_other_regions filters are included. Results are sorted by display
    code A-Z; streams within each country by product_name then sort_order.
    """
    if geolocation is None or not geolocation.country:
        return []

    user_country = geolocation.country
    if user_country not in WATCH_LINKS:
        return []

    results: list[tuple[str, list[WatchLinkEntry]]] = []
    for iso, country_data in WATCH_LINKS.items():
        if iso == user_country:
            continue  # skip user's own country

        streams = _other_region_streams(_flatten_country_streams(country_data))
        if not streams:
            continue

        results.append((_country_display_code(iso), streams))

    results.sort(key=lambda entry: entry[0])  # entry[0] is the display country code string
    return results
