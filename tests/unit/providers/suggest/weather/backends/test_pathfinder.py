# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Accuweather pathfinder module."""

from typing import Tuple

import pytest

from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    compass,
    set_region_mapping,
    clear_region_mapping,
)


@pytest.mark.parametrize(
    ("location", "expected_region_and_city"),
    [
        (
            Location(country="CA", regions=["BC"], city="Vancouver"),
            ("BC", "Vancouver"),
        ),
        (
            Location(country="IT", regions=["MT", "77"], city="Matera"),
            ("77", "Matera"),
        ),
        (
            Location(country="AR", regions=["B", "5"], city="La Plata"),
            ("STE", "La Plata"),
        ),
        (
            Location(country="BR", regions=["DF"], city="Brasilia"),
            ("DF", "Brasilia"),
        ),
        (
            Location(country="IE", regions=None, city="Dublin"),
            (None, "Dublin"),
        ),
        (
            Location(country="CA", regions=["ON"], city="Mitchell/Ontario"),
            ("ON", "Mitchell"),
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
def test_compass(location: Location, expected_region_and_city: Tuple) -> None:
    """Test country that returns the most specific region."""
    set_region_mapping("AR", "La Plata", "STE")
    assert next(compass(location)) == expected_region_and_city

    clear_region_mapping()
