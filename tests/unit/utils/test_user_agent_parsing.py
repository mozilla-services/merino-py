# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the user_agent_parsing.py utility module."""

import pytest

from merino.utils.user_agent_parsing import parse

Scenario = tuple[str, str, str, str]

SCENARIOS: list[Scenario] = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2; rv:85.0) Gecko/20100101 Firefox/103.0",
        "Firefox(103.0)",
        "macos",
        "desktop",
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:104.0) Gecko/20100101 Firefox/104.0.1",
        "Firefox(104.0.1)",
        "windows",
        "desktop",
    ),
    (
        "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:82.0.1) Gecko/20100101 Firefox/106.0a1",
        "Firefox(106.0.a1)",
        "linux",
        "desktop",
    ),
    (
        "Mozilla/5.0 (Android 11; Mobile; rv:68.0) Gecko/68.0 Firefox/105.0",
        "Firefox(105.0)",
        "android",
        "phone",
    ),
    (
        "Mozilla/5.0 (Android 11; Tablet; rv:68.0) Gecko/41.0 Firefox/105.0",
        "Firefox(105.0)",
        "android",
        "tablet",
    ),
    (
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 12_5_1 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) FxiOS/104.0 Mobile/15E148 Safari/605.1.15"
        ),
        "Firefox(104.0)",
        "ios",
        "phone",
    ),
    (
        (
            "Mozilla/5.0 (iPad; CPU OS 12_5_1 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) FxiOS/104.0 Mobile/15E148 Safari/605.1.15"
        ),
        "Firefox(104.0)",
        "ios",
        "tablet",
    ),
    (
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) Version/13.1 Safari/605.1.15"
        ),
        "Safari",
        "macos",
        "desktop",
    ),
    (
        (
            "Mozilla/5.0 (X11; CrOS x86_64 13816.64.0) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/90.0.4430.100 Safari/537.36"
        ),
        "Chrome",
        "chromeos",
        "other",
    ),
    ("curl/7.84.0", "curl", "other", "other"),
    ("", "Other", "other", "other"),
]


@pytest.mark.parametrize(
    ["ua", "expected_browser", "expected_os_family", "expected_form_factor"],
    SCENARIOS,
)
def test_ua_parsing(ua, expected_browser, expected_os_family, expected_form_factor):
    """
    Test that the parse method assigns the 'browser', 'os_family' and 'form_factor'
    values as expected from a User-Agent heading.
    """
    result = parse(ua)

    assert result["browser"] == expected_browser
    assert result["os_family"] == expected_os_family
    assert result["form_factor"] == expected_form_factor
