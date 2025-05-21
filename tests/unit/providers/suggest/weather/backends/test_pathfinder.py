# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Accuweather pathfinder module."""

from unittest.mock import AsyncMock

import pytest

from merino.middleware.geolocation import Location
from merino.providers.suggest.weather.backends.accuweather.pathfinder import (
    compass,
    set_region_mapping,
    clear_region_mapping,
    normalize_string,
    remove_locality_suffix,
    explore,
)
from merino.providers.suggest.weather.backends.protocol import WeatherContext


@pytest.mark.parametrize(
    ("location", "expected_region_and_city"),
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
            Location(country="AA", regions=["B", "5"], city="La Plata"),
            "STE",
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
        (
            Location(country="IT", regions=["33", "09"], city="Milan"),
            "25",
        ),
    ],
    ids=[
        "Specific Region Country",
        "Alternative Region Country",
        "Successful Region Mapping Pair",
        "Fallback with Region",
        "Fallback No Region",
        "Corrected City Name",
        "FIP region Mapped",
    ],
)
def test_compass(location: Location, expected_region_and_city: str) -> None:
    """Test country that returns the most specific region."""
    # Changed this to a fake country code, as we add more countries
    # this test will fail, with a real country code
    set_region_mapping("AA", "La Plata", "STE")
    assert next(compass(location)) == expected_region_and_city

    clear_region_mapping()


@pytest.mark.parametrize(
    ("weather_context", "expected_calls_count"),
    [
        (
            WeatherContext(
                Location(country="AA", regions=["BC"], city="Accènted City"), languages=["en-US"]
            ),
            6,
        ),
        (
            WeatherContext(
                Location(country="CA", regions=["BC"], city="Plain"), languages=["en-US"]
            ),
            1,
        ),
    ],
)
@pytest.mark.asyncio
async def test_explore_uses_all_the_right_city_combos(
    weather_context: WeatherContext, expected_calls_count: int
) -> None:
    """Test we try the number of right cities."""
    mock_probe = AsyncMock(return_value=None)

    _ = await explore(weather_context, mock_probe)
    assert len(mock_probe.call_args_list) == expected_calls_count


@pytest.mark.parametrize(
    "input_string, expected_output",
    [
        ("Köseköy", "Kosekoy"),
        ("Kīhei", "Kihei"),
        ("Llambí Campbell", "Llambi Campbell"),
        ("Luis Eduardo Magalhães", "Luis Eduardo Magalhaes"),
        ("México", "Mexico"),
        ("Minamirokugō", "Minamirokugo"),
        ("Orléans", "Orleans"),
    ],
)
def test_normalize_string(input_string, expected_output) -> None:
    """Test the normalization of strings with special characters"""
    assert normalize_string(input_string) == expected_output


@pytest.mark.parametrize(
    "input_string, expected_output",
    [
        ("Querétaro City", "Querétaro"),
        ("Centro Municipality", "Centro"),
        ("Burnaby", "Burnaby"),
    ],
)
def test_remove_locality_suffix(input_string, expected_output) -> None:
    """Test locality suffix is removed"""
    assert remove_locality_suffix(input_string) == expected_output
