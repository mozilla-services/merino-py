# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.utils."""

import pytest

from merino.middleware.geolocation import Location
from merino.providers.wcs.utils import get_team_colours, resolve_other_regions, resolve_watch_links
from merino.providers.wcs.watch_links import CountryEntry, build_watch_link


def test_get_team_colours_returns_hex_colours_for_valid_team() -> None:
    """France colours are returned as a list of hex strings."""
    colours = get_team_colours("FRA")
    assert colours == ["#0055A4", "#FFFFFF", "#EF4135"]


def test_get_team_colours_returns_empty_list_for_invalid_team() -> None:
    """Empty list returned for Italy."""
    colours = get_team_colours("ITA")
    assert colours == []


#################################
#                               #
#       shared test helpers     #
#                               #
#################################

_US = Location(country="US")
_UNCOVERED = Location(country="ZZ")  # not present in mock data

_URL = "https://example.com"


@pytest.fixture(name="mock_watch_links")
def mock_watch_links(mocker):
    """Patch WATCH_LINKS with minimal deterministic test data.

    US has "en" streams (one unpublished), a '*' wildcard, and is the user's own country
    in most tests. GB and DE have qualifying other-region streams; FR has only an
    unpublished stream and is therefore excluded from other-regions results.
    """
    data: dict[str, CountryEntry] = {
        "US": {
            "dau": 1_000,
            "langs": {
                "en": [
                    build_watch_link(
                        "Alpha",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                    build_watch_link(
                        "Bravo",
                        _URL,
                        sort_order=4,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                    build_watch_link(
                        "Unpublished",
                        _URL,
                        sort_order=2,
                        in_production=False,
                        show_in_other_regions=True,
                    ),
                ],
                "*": [
                    build_watch_link(
                        "Wildcard",
                        _URL,
                        sort_order=1,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                ],
            },
        },
        "GB": {
            "dau": 500,
            "langs": {
                "en": [
                    build_watch_link(
                        "BBC",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                    build_watch_link(
                        "ITV",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=False,
                    ),
                ],
            },
        },
        "DE": {
            "dau": 300,
            "langs": {
                "de": [
                    build_watch_link(
                        "ZDF",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                    build_watch_link(
                        "ARD",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    ),
                ],
            },
        },
        "FR": {
            "dau": 200,
            "langs": {
                "fr": [
                    build_watch_link(
                        "M6",
                        _URL,
                        sort_order=2,
                        in_production=False,
                        show_in_other_regions=True,
                    ),
                ],
            },
        },
    }
    mocker.patch("merino.providers.wcs.utils.WATCH_LINKS", data)
    return data


#####################################
#                                   #
#    resolve_watch_links() tests    #
#                                   #
#####################################


def test_resolve_watch_links_no_geolocation_returns_empty(mock_watch_links) -> None:
    """Returns empty list when geolocation is None."""
    assert resolve_watch_links(None, ["en"]) == []


def test_resolve_watch_links_country_not_covered_returns_empty(mock_watch_links) -> None:
    """Returns empty list when the country is not in WATCH_LINKS."""
    assert resolve_watch_links(_UNCOVERED, ["en"]) == []


def test_resolve_watch_links_language_match_returns_lang_streams(mock_watch_links) -> None:
    """Matching language key returns its in-production streams."""
    result = resolve_watch_links(_US, ["en-US"])
    names = [link.product_name for link in result]
    assert "Alpha" in names
    assert "Bravo" in names
    assert "Unpublished" not in names


def test_resolve_watch_links_wildcard_merged_with_lang_entries(mock_watch_links) -> None:
    """'*' wildcard streams are always merged with language-specific streams."""
    result = resolve_watch_links(_US, ["en"])
    names = [link.product_name for link in result]
    assert "Wildcard" in names
    assert "Alpha" in names


def test_resolve_watch_links_no_language_match_returns_wildcard_only(mock_watch_links) -> None:
    """When no language key matches, only '*' streams are returned."""
    result = resolve_watch_links(_US, ["zh"])
    assert len(result) == 1
    assert result[0].product_name == "Wildcard"


def test_resolve_watch_links_highest_priority_language_wins(mocker) -> None:
    """First accepted language that matches a key is used; later ones are ignored."""
    data: dict[str, CountryEntry] = {
        "BE": {
            "dau": 100,
            "langs": {
                "fr": [
                    build_watch_link(
                        "RTBF",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    )
                ],
                "nl": [
                    build_watch_link(
                        "VRT",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    )
                ],
            },
        },
    }
    mocker.patch("merino.providers.wcs.utils.WATCH_LINKS", data)

    result = resolve_watch_links(Location(country="BE"), ["fr", "nl"])
    assert [link.product_name for link in result] == ["RTBF"]


def test_resolve_watch_links_in_production_false_filtered(mock_watch_links) -> None:
    """Streams with in_production=False are excluded from results."""
    result = resolve_watch_links(_US, ["en"])
    assert all(link.in_production for link in result)


def test_resolve_watch_links_sorted_by_sort_order_then_product_name(mock_watch_links) -> None:
    """Results are sorted by sort_order ascending, then product_name ascending as tie-break."""
    result = resolve_watch_links(_US, ["en"])
    assert [link.product_name for link in result] == ["Wildcard", "Alpha", "Bravo"]


#####################################
#                                   #
#    resolve_other_regions() tests  #
#                                   #
#####################################


def test_resolve_other_regions_no_geolocation_returns_empty(mock_watch_links) -> None:
    """Returns empty list when geolocation is None."""
    assert resolve_other_regions(None) == []


def test_resolve_other_regions_user_country_excluded(mock_watch_links) -> None:
    """The user's own country does not appear in results."""
    result = resolve_other_regions(_US)
    country_codes = [country for country, _ in result]
    assert "USA" not in country_codes


def test_resolve_other_regions_country_with_no_qualifying_streams_excluded(
    mock_watch_links,
) -> None:
    """Countries where all streams fail the filter are omitted entirely."""
    result = resolve_other_regions(_US)
    # FR has only in_production=False streams
    country_codes = [country for country, _ in result]
    assert "FRA" not in country_codes


def test_resolve_other_regions_show_in_other_regions_false_filtered(mock_watch_links) -> None:
    """Streams with show_in_other_regions=False are excluded."""
    result = resolve_other_regions(_US)
    uk_streams = next((streams for code, streams in result if code == "UK"), [])
    names = [link.product_name for link in uk_streams]
    assert "BBC" in names
    assert "ITV" not in names


def test_resolve_other_regions_in_production_false_filtered(mock_watch_links) -> None:
    """Streams with in_production=False are excluded."""
    result = resolve_other_regions(_US)
    all_streams = [e for _, streams in result for e in streams]
    assert all(link.in_production for link in all_streams)


def test_resolve_other_regions_all_language_keys_included(mocker) -> None:
    """Streams from every language key are pooled regardless of the user's language."""
    data: dict[str, CountryEntry] = {
        "US": {
            "dau": 1_000,
            "langs": {
                "en": [
                    build_watch_link(
                        "US Only",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=False,
                    )
                ]
            },
        },
        "BE": {
            "dau": 100,
            "langs": {
                "fr": [
                    build_watch_link(
                        "RTBF",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    )
                ],
                "nl": [
                    build_watch_link(
                        "VRT",
                        _URL,
                        sort_order=2,
                        in_production=True,
                        show_in_other_regions=True,
                    )
                ],
            },
        },
    }
    mocker.patch("merino.providers.wcs.utils.WATCH_LINKS", data)

    result = resolve_other_regions(Location(country="US"))
    assert len(result) == 1
    _, streams = result[0]
    names = [link.product_name for link in streams]
    assert "RTBF" in names
    assert "VRT" in names


def test_resolve_other_regions_countries_sorted_by_display_code(mock_watch_links) -> None:
    """Countries are sorted by their display code A-Z."""
    result = resolve_other_regions(_US)
    country_codes = [code for code, _ in result]
    assert country_codes == sorted(country_codes)


def test_resolve_other_regions_streams_sorted_by_product_name_then_sort_order(
    mock_watch_links,
) -> None:
    """Streams within a country are sorted by product_name then sort_order."""
    result = resolve_other_regions(_US)
    de_streams = next((streams for code, streams in result if code == "GER"), [])
    # ARD and ZDF both have sort_order=2; alphabetically ARD < ZDF
    assert [link.product_name for link in de_streams] == ["ARD", "ZDF"]
