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
