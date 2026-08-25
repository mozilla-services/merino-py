# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the weather backend protocol module."""

import pytest

from merino.providers.suggest.weather.backends.protocol import Temperature


@pytest.mark.parametrize(
    ["parameters", "expected"],
    [
        ({"c": 1.0}, {"c": 1.0, "f": 34.0}),
        ({"c": 1.1}, {"c": 1.0, "f": 34.0}),
        ({"c": 1.5}, {"c": 2.0, "f": 35.0}),
        ({"c": 0.0}, {"c": 0.0, "f": 32.0}),
        ({"c": -1.0}, {"c": -1.0, "f": 30.0}),
        ({"c": -1.1}, {"c": -1.0, "f": 30.0}),
        ({"c": -1.5}, {"c": -2.0, "f": 29.0}),
        ({"f": 1.0}, {"c": -17.0, "f": 1.0}),
        ({"f": 1.1}, {"c": -17.0, "f": 1.0}),
        ({"f": 1.5}, {"c": -17.0, "f": 2.0}),
        ({"f": 0.0}, {"c": -18.0, "f": 0.0}),
        ({"f": -1.0}, {"c": -18.0, "f": -1.0}),
        ({"f": -1.1}, {"c": -18.0, "f": -1.0}),
        ({"f": -1.5}, {"c": -19.0, "f": -2.0}),
        ({"c": 10, "f": 70}, {"c": 10, "f": 70}),
        ({}, {"c": None, "f": None}),
    ],
    ids=[
        "c_positive",
        "c_positive_round_down",
        "c_positive_round_up",
        "c_zero",
        "c_negative",
        "c_negative_round_up",
        "c_negative_round_down",
        "f_positive",
        "f_positive_round_down",
        "f_positive_round_up",
        "f_zero",
        "f_negative",
        "f_negative_round_up",
        "f_negative_round_down",
        "mismatch",
        "empty",
    ],
)
def test_temperature(parameters: dict[str, float], expected: dict[str, float]) -> None:
    """Test that Temperature values evaluate as expected given different parameters."""
    temperature: Temperature = Temperature(**parameters)

    assert temperature == Temperature(**expected)
