# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the AdM provider unit test directory."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from merino.providers.adm.backends.protocol import AdmBackend, SuggestionContent
from merino.providers.adm.provider import Provider


@pytest.fixture(name="adm_suggestion_content")
def fixture_adm_suggestion_content() -> SuggestionContent:
    """Define backend suggestion content for test."""
    return SuggestionContent(
        suggestions={
            "firefox": (0, 0),
            "firefox account": (0, 0),
            "firefox accounts": (0, 0),
            "mozilla": (0, 1),
            "mozilla firefox": (0, 1),
            "mozilla firefox account": (0, 1),
            "mozilla firefox accounts": (0, 1),
        },
        full_keywords=["firefox accounts", "mozilla firefox accounts"],
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
            }
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
