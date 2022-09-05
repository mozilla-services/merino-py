# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from typing import Any

import httpx
import pytest

from merino.providers.adm import Provider


class FakeRSClient:
    """Fake Remote Settings client that returns suggest data for tests."""

    async def get(self, bucket: Any, collection: Any) -> list[dict[Any, Any]]:
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

    async def fetch_attachment(self, attachement_uri: Any) -> httpx.Response:
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

        return httpx.Response(200, text=json.dumps([attachments[attachement_uri]]))

    def get_icon_url(self, icon_uri: str) -> str:
        """Return a fake icon URL for the given URI."""

        return f"attachment-host/{icon_uri}"


@pytest.fixture(name="adm")
def fixture_adm() -> Provider:
    """Return an adM provider that uses a fake remote settings client."""

    return Provider(rs_client=FakeRSClient())


def test_enabled_by_default(adm: Provider) -> None:
    """Test for the enabled_by_default method."""

    assert adm.enabled_by_default() is True


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
