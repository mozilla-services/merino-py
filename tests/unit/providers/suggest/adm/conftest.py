# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the AdM provider unit test directory."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.providers.suggest.adm.backends.protocol import AdmBackend, SuggestionContent
from merino.providers.suggest.adm.provider import Provider


@pytest.fixture(name="adm_suggestion_content")
def fixture_adm_suggestion_content() -> SuggestionContent:
    """Define backend suggestion content for test."""
    return SuggestionContent(
        suggestions={
            "US": {
                (("desktop",), "firefox"): (0, 0),
                (("desktop",), "firefox account"): (0, 0),
                (("desktop",), "firefox accounts"): (0, 0),
                (("desktop",), "mozilla"): (0, 1),
                (("desktop",), "mozilla firefox"): (0, 1),
                (("desktop",), "mozilla firefox account"): (0, 1),
                (("desktop",), "mozilla firefox accounts"): (0, 1),
            },
            "DE": {
                (("phone",), "firefox"): (1, 2),
                (("phone",), "firefox account"): (1, 2),
                (("phone",), "firefox accounts de"): (1, 2),
                (("phone",), "mozilla"): (1, 3),
                (("phone",), "mozilla firefox"): (1, 3),
                (("phone",), "mozilla firefox account"): (1, 3),
                (("phone",), "mozilla firefox accounts de"): (1, 3),
            },
        },
        full_keywords=[
            "firefox accounts",
            "mozilla firefox accounts",
            "firefox accounts de",
            "mozilla firefox accounts de",
        ],
        results=[
            {
                "id": 2,
                "url": "https://example.org/target/mozfirefoxaccounts",
                "click_url": "https://example.org/click/mozilla",
                "impression_url": "https://example.org/impression/mozilla",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "Example.org",
                "title": "Mozilla Firefox Accounts",
            },
            {
                "id": 3,
                "url": "https://de.example.org/target/mozfirefoxaccounts",
                "click_url": "https://de.example.org/click/mozilla",
                "impression_url": "https://de.example.org/impression/mozilla",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "de.Example.org",
                "title": "Mozilla Firefox Accounts",
            },
        ],
        icons={"01": "attachment-host/main-workspace/quicksuggest/icon-01"},
    )


@pytest.fixture(name="adm_parameters")
def fixture_adm_parameters() -> dict[str, Any]:
    """Define provider parameters for test."""
    return {
        "score": 0.3,
        "name": "adm",
        "resync_interval_sec": 10800,
        "cron_interval_sec": 60,
    }


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture, adm_suggestion_content: SuggestionContent) -> Any:
    """Create an AdmBackend mock object for test."""
    backend_mock: Any = mocker.AsyncMock(spec=AdmBackend)
    backend_mock.fetch.return_value = adm_suggestion_content
    return backend_mock


@pytest.fixture(name="adm")
def fixture_adm(backend_mock: Any, adm_parameters: dict[str, Any]) -> Provider:
    """Create an AdM Provider for test."""
    return Provider(backend=backend_mock, **adm_parameters)
