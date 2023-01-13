# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm provider module."""

import json
from typing import Any

import httpx
import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.providers.adm.backends.protocol import AdmBackend
from merino.providers.adm.provider import NonsponsoredSuggestion, Provider
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture


class FakeBackend:
    """Fake Remote Settings backend that returns suggest data for tests."""

    async def get(self) -> list[dict[str, Any]]:
        """Return fake records."""
        return [
            {
                "type": "data",
                "schema": 123,
                "attachment": {
                    "hash": "abcd",
                    "size": 1,
                    "filename": "data-01.json",
                    "location": "main-workspace/quicksuggest/attachmment-01.json",
                    "mimetype": "application/octet-stream",
                },
                "id": "data-01",
                "last_modified": 123,
            },
            {
                "type": "offline-expansion-data",
                "schema": 111,
                "attachment": {
                    "hash": "efgh",
                    "size": 1,
                    "filename": "offline-expansion-data-01.json",
                    "location": "main-workspace/quicksuggest/attachment-02.json",
                    "mimetype": "application/octet-stream",
                },
                "id": "offline-expansion-data-01",
                "last_modified": 123,
            },
            {
                "type": "icon",
                "schema": 456,
                "attachment": {
                    "hash": "efghabcasd",
                    "size": 1,
                    "filename": "icon-01",
                    "location": "main-workspace/quicksuggest/icon-01",
                    "mimetype": "application/octet-stream",
                },
                "content_type": "image/png",
                "id": "icon-01",
                "last_modified": 123,
            },
        ]

    async def fetch_attachment(self, attachment_uri: str) -> httpx.Response:
        """Return a fake attachment for the given URI."""
        attachments = {
            "main-workspace/quicksuggest/attachmment-01.json": {
                "id": 1,
                "url": "https://example.com/target/helloworld",
                "click_url": "https://example.com/click/helloworld",
                "impression_url": "https://example.com/impression/helloworld",
                "iab_category": "22 - Shopping",
                "icon": "01",
                "advertiser": "Example.com",
                "title": "Hello World",
                "keywords": ["hello", "world", "hello world"],
                "full_keywords": [("hello world", 3)],
            },
            "main-workspace/quicksuggest/attachment-02.json": {
                "id": 2,
                "url": "https://example.org/target/mozfirefoxaccounts",
                "click_url": "https://example.org/click/mozilla",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "Example.org",
                "title": "Mozilla Firefox Accounts",
                "keywords": [
                    "firefox",
                    "firefox account",
                    "firefox accounts",
                    "mozilla",
                    "mozilla firefox",
                    "mozilla firefox account",
                    "mozilla firefox accounts",
                ],
                "full_keywords": [
                    ("firefox accounts", 3),
                    ("mozilla firefox accounts", 4),
                ],
            },
        }

        return httpx.Response(200, text=json.dumps([attachments[attachment_uri]]))

    def get_icon_url(self, icon_uri: str) -> str:
        """Return a fake icon URL for the given URI."""
        return f"attachment-host/{icon_uri}"


@pytest.fixture(name="adm_parameters")
def fixture_adm_parameters() -> dict[str, Any]:
    """Define provider parameters for test."""
    return {
        "score": 0.3,
        "score_wikipedia": 0.2,
        "name": "adm",
        "resync_interval_sec": 10800,
    }


@pytest.fixture(name="adm")
def fixture_adm(adm_parameters: dict[str, Any]) -> Provider:
    """Create an AdM Provider for test using a fake backend."""
    return Provider(backend=FakeBackend(), **adm_parameters)


def test_enabled_by_default(adm: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert adm.enabled_by_default is True


def test_hidden(adm: Provider) -> None:
    """Test for the hidden method."""
    assert adm.hidden() is False


@pytest.mark.asyncio
async def test_initialize(adm: Provider) -> None:
    """Test for the initialize() method of the adM provider."""
    await adm.initialize()

    assert adm.suggestions == {
        "firefox": (0, 0),
        "firefox account": (0, 0),
        "firefox accounts": (0, 0),
        "mozilla": (0, 1),
        "mozilla firefox": (0, 1),
        "mozilla firefox account": (0, 1),
        "mozilla firefox accounts": (0, 1),
    }
    assert adm.results == [
        {
            "id": 2,
            "url": "https://example.org/target/mozfirefoxaccounts",
            "click_url": "https://example.org/click/mozilla",
            "iab_category": "5 - Education",
            "icon": "01",
            "advertiser": "Example.org",
            "title": "Mozilla Firefox Accounts",
        }
    ]
    assert adm.icons == {1: "attachment-host/main-workspace/quicksuggest/icon-01"}


@pytest.mark.asyncio
async def test_initialize_remote_settings_failure(
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    adm_parameters: dict[str, Any],
) -> None:
    """Test exception handling for the initialize() method."""
    error_message: str = "The remote server was unreachable"
    backend_mock: Any = mocker.AsyncMock(spec=AdmBackend)
    backend_mock.get.side_effect = Exception(error_message)
    adm: Provider = Provider(backend=backend_mock, **adm_parameters)

    try:
        await adm.initialize()
    finally:
        # Clean up the cron task. Unlike other test cases, this action is necessary here
        # since the cron job has kicked in as the initial fetch fails.
        adm.cron_task.cancel()

    records = filter_caplog(caplog.records, "merino.providers.adm.provider")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == error_message
    assert adm.last_fetch_at == 0


@pytest.mark.asyncio
async def test_query_success(srequest: SuggestionRequestFixture, adm: Provider) -> None:
    """Test for the query() method of the adM provider."""
    await adm.initialize()

    res = await adm.query(srequest("firefox"))
    assert res == [
        NonsponsoredSuggestion(
            block_id=2,
            full_keyword="firefox accounts",
            title="Mozilla Firefox Accounts",
            url="https://example.org/target/mozfirefoxaccounts",
            impression_url=None,
            click_url="https://example.org/click/mozilla",
            provider="adm",
            advertiser="Example.org",
            is_sponsored=False,
            icon="attachment-host/main-workspace/quicksuggest/icon-01",
            score=0.3,
        )
    ]


@pytest.mark.asyncio
async def test_query_with_missing_key(
    srequest: SuggestionRequestFixture, adm: Provider
) -> None:
    """Test for the query() method of the adM provider with a missing key."""
    await adm.initialize()

    assert await adm.query(srequest("nope")) == []
