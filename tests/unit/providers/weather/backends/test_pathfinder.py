# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Accuweather pathfinder module."""

from typing import Tuple

import pytest

from merino.middleware.geolocation import Location
from merino.providers.weather.backends.accuweather.pathfinder import (
    compass,
    set_region_mapping,
    clear_region_mapping,
)


@pytest.mark.parametrize(
    ("location", "expected_tuple"),
    [
        (
            Location(country="CA", regions=["BC"], city="Vancouver"),
            "BC",
        ),
        (
            Location(country="IT", regions=["MT", "77"], city="Matera"),
            "77",
        ),
        (
            Location(country="GB", regions=["ENG", "HWT"], city="London"),
            "LND",
        ),
        (
            Location(country="BR", regions=["DF"], city="Brasilia"),
            "DF",
        ),
        (
            Location(country="IE", regions=None, city="Dublin"),
            None,
        ),
        (
            Location(country="CA", regions=["ON"], city="Mitchell/Ontario"),
            "ON",
        ),
    ],
    ids=[
        "Specific Region Country",
        "Alternative Region Country",
        "Successful Region Mapping Pair",
        "Fallback with Region",
        "Fallback No Region",
        "Corrected City Name",
    ],
)
def test_compass(location: Location, expected_tuple: Tuple) -> None:
    """Test country that returns the most specific region."""
    set_region_mapping("GB", "London", "LND")

    assert next(compass(location)) == expected_tuple

    clear_region_mapping()
