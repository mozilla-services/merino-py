# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather backend protocol module."""

import pytest

from merino.providers.weather.backends.protocol import Temperature


@pytest.mark.parametrize(
    ["parameters", "expected"],
    [
        ({"c": 1.0}, {"c": 1.0, "f": 34.0}),
        ({"c": 0.0}, {"c": 0.0, "f": 32.0}),
        ({"c": -1.0}, {"c": -1.0, "f": 30.0}),
        ({"f": 1.0}, {"c": -17.2, "f": 1.0}),
        ({"f": 0.0}, {"c": -17.8, "f": 0.0}),
        ({"f": -1.0}, {"c": -18.3, "f": -1.0}),
        ({"c": 10, "f": 70}, {"c": 10, "f": 70}),
        ({}, {"c": None, "f": None}),
    ],
    ids=[
        "c_positive",
        "c_zero",
        "c_negative",
        "f_positive",
        "f_zero",
        "f_negative",
        "mismatch",
        "empty",
    ],
)
def test_temperature(parameters: dict[str, float], expected: dict[str, float]) -> None:
    """Test that Temperature values evaluate as expected given different parameters."""
    temperature: Temperature = Temperature(**parameters)

    assert temperature == expected
