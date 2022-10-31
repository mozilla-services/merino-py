# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import logging
from typing import Any

import httpx
import pytest
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.adm import NonsponsoredSuggestion, Provider
from tests.unit.web.util import filter_caplog, srequest


class FakeBackend:
    """Fake Remote Settings backend that returns suggest data for tests."""

    async def get(self, bucket: str, collection: str) -> list[dict[str, Any]]:
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
            },
            "main-workspace/quicksuggest/attachment-02.json": {
                "id": 2,
                "url": "https://example.org/target/banana",
                "click_url": "https://example.org/click/banana",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "Example.org",
                "title": "Hello Banana",
                "keywords": ["hello", "banana", "hello banana"],
            },
        }

        return httpx.Response(200, text=json.dumps([attachments[attachment_uri]]))

    def get_icon_url(self, icon_uri: str) -> str:
        """Return a fake icon URL for the given URI."""

        return f"attachment-host/{icon_uri}"


@pytest.fixture(name="adm")
def fixture_adm() -> Provider:
    """Return an adM provider that uses a fake remote settings client."""

    return Provider(backend=FakeBackend())


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

    assert adm.suggestions == {"banana": 0, "hello": 0, "hello banana": 0}
    assert adm.results == [
        {
            "id": 2,
            "url": "https://example.org/target/banana",
            "click_url": "https://example.org/click/banana",
            "iab_category": "5 - Education",
            "icon": "01",
            "advertiser": "Example.org",
            "title": "Hello Banana",
        }
    ]
    assert adm.icons == {1: "attachment-host/main-workspace/quicksuggest/icon-01"}


@pytest.mark.asyncio
async def test_initialize_failure(
    adm: Provider,
    mocker: MockerFixture,
    caplog: Any,
) -> None:
    """Test exception handling for the initialize() method."""

    caplog.set_level(logging.WARNING)
    mocker.patch.object(
        adm, "_fetch", side_effect=Exception("The remote server was unreachable")
    )

    await adm.initialize()

    try:
        records = filter_caplog(caplog.records, "merino.providers.adm")

        assert adm.last_fetch_at == 0

        assert len(records) == 1
        assert (
            records[0].__dict__["error message"] == "The remote server was unreachable"
        )
    finally:
        # Clean up the cron task. Unlike other test cases, this action is necessary here
        # since the cron job has kicked in as the initial fetch fails.
        adm.cron_task.cancel()


@pytest.mark.asyncio
async def test_query_success(adm: Provider) -> None:
    """Test for the query() method of the adM provider."""

    await adm.initialize()

    res = await adm.query(srequest("banana"))
    assert res == [
        NonsponsoredSuggestion(
            block_id=2,
            full_keyword="banana",
            title="Hello Banana",
            url="https://example.org/target/banana",
            impression_url=None,
            click_url="https://example.org/click/banana",
            provider="adm",
            advertiser="Example.org",
            is_sponsored=False,
            icon="attachment-host/main-workspace/quicksuggest/icon-01",
            score=settings.providers.adm.score,
        )
    ]


@pytest.mark.asyncio
async def test_query_with_missing_key(adm: Provider) -> None:
    """Test for the query() method of the adM provider with a missing key."""

    await adm.initialize()

    assert await adm.query(srequest("nope")) == []
