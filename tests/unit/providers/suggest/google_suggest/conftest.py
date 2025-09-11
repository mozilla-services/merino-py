# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the Google Suggest unit tests."""

import pytest

from merino.providers.suggest.google_suggest.backends.protocol import GoogleSuggestResponse


@pytest.fixture(name="google_suggest_response")
def fixture_google_suggest_response() -> GoogleSuggestResponse:
    """Return a test Google Suggest response."""
    return [
        "toronto",
        [
            "toronto blue jays",
            "toronto weather",
            "toronto blue jays standings",
            "toronto blue jays schedule",
            "toronto maple leafs",
            "toronto police",
            "toronto sun",
            "toronto",
            "toronto zoo",
            "toronto news",
        ],
        [],
        {
            "google:suggestsubtypes": [
                [512, 433, 131],
                [512, 433, 131],
                [512, 433, 131],
                [512, 433, 131],
                [512, 433],
                [512, 433, 131],
                [512, 433, 131],
                [512, 433],
                [512, 433],
                [512, 433, 131],
            ]
        },
    ]
