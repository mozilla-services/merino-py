# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Suggest API language header filtering."""

import pytest

from merino.web.api_v1 import get_accepted_languages


@pytest.mark.parametrize(
    ("languages", "expected_filtered_languages"),
    [
        ("*", ["en-US"]),
        ("en-US", ["en-US"]),
        ("en-US,en;q=0.5", ["en-US", "en"]),
        ("en-US,en;q=0.9,zh-CN;q=0.7", ["en-US", "en", "zh-CN"]),
        ("en-CA;q=invalid", ["en-US"]),
    ],
)
def test_get_accepted_languages(languages, expected_filtered_languages):
    """Test Accept-Language Header parsing and filtering."""
    assert get_accepted_languages(languages) == expected_filtered_languages
