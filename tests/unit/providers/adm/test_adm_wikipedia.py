# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm-wikipedia provider module."""

import json
from typing import Any

import httpx
import pytest

from merino.config import settings
from merino.providers.adm.adm import NonsponsoredSuggestion, Provider
from tests.unit.types import SuggestionRequestFixture


class FakeBackend:
    """Fake Remote Settings backend that returns suggest data for tests."""

    async def get(self, bucket: str, collection: str) -> list[dict[str, Any]]:
        """Return fake records."""
        return [
            {
                "type": "data",
                "schema": 111,
                "attachment": {
                    "hash": "efgh",
                    "size": 1,
                    "filename": "data-01.json",
                    "location": "main-workspace/quicksuggest/attachment-01.json",
                    "mimetype": "application/octet-stream",
                },
                "id": "data-01",
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
            "main-workspace/quicksuggest/attachment-01.json": {
                "id": 1,
                "url": "https://wikipedia.org/en/Mozilla",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "Wikipedia",
                "title": "Mozilla",
                "keywords": ["mozilla"],
                "full_keywords": [["mozilla", 1]],
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


@pytest.mark.asyncio
async def test_initialize(adm: Provider) -> None:
    """Test for the initialize() method of the adM provider."""
    await adm.initialize()

    assert adm.suggestions == {"mozilla": (0, 0)}
    assert adm.results == [
        {
            "id": 1,
            "url": "https://wikipedia.org/en/Mozilla",
            "iab_category": "5 - Education",
            "icon": "01",
            "advertiser": "Wikipedia",
            "title": "Mozilla",
        },
    ]
    assert adm.icons == {1: "attachment-host/main-workspace/quicksuggest/icon-01"}


@pytest.mark.asyncio
async def test_wikipedia_specific_score(
    srequest: SuggestionRequestFixture, adm: Provider
) -> None:
    """Test for the query() method of the adM provider."""
    await adm.initialize()

    res = await adm.query(srequest("mozilla"))
    assert res == [
        NonsponsoredSuggestion(
            block_id=1,
            full_keyword="mozilla",
            title="Mozilla",
            url="https://wikipedia.org/en/Mozilla",
            impression_url=None,
            click_url=None,
            provider="adm",
            advertiser="Wikipedia",
            is_sponsored=False,
            icon="attachment-host/main-workspace/quicksuggest/icon-01",
            score=settings.providers.adm.score_wikipedia,
        )
    ]
