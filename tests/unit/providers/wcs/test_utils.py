# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.utils."""

from merino.providers.wcs.utils import get_team_colours


def test_get_team_colours_returns_hex_colours_for_valid_team() -> None:
    """France colours are returned as a list of hex strings."""
    colours = get_team_colours("FRA")
    assert colours == ["#0055A4", "#FFFFFF", "#EF4135"]


def test_get_team_colours_returns_empty_list_for_invalid_team() -> None:
    """Empty list returned for Italy."""
    colours = get_team_colours("ITA")
    assert colours == []
