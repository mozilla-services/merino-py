# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm-wikipedia provider module."""

from typing import Any

import pytest

from merino.providers.adm.backends.protocol import SuggestionContent
from merino.providers.adm.provider import NonsponsoredSuggestion, Provider
from tests.unit.types import SuggestionRequestFixture


@pytest.fixture(name="adm_suggestion_content")
def fixture_adm_suggestion_content() -> SuggestionContent:
    """Define backend suggestion content for test.
    This fixture overrides a fixture of the same name in conftest.py
    """
    return SuggestionContent(
        suggestions={"mozilla": (0, 0)},
        full_keywords=["mozilla"],
        results=[
            {
                "id": 1,
                "url": "https://wikipedia.org/en/Mozilla",
                "iab_category": "5 - Education",
                "icon": "01",
                "advertiser": "Wikipedia",
                "title": "Mozilla",
            }
        ],
        icons={1: "attachment-host/main-workspace/quicksuggest/icon-01"},
    )


@pytest.mark.asyncio
async def test_initialize(
    adm: Provider, adm_suggestion_content: SuggestionContent
) -> None:
    """Test for the initialize() method of the adM provider."""
    await adm.initialize()

    assert adm.suggestion_content == adm_suggestion_content
    assert adm.last_fetch_at > 0


@pytest.mark.asyncio
async def test_wikipedia_specific_score(
    srequest: SuggestionRequestFixture, adm: Provider, adm_parameters: dict[str, Any]
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
            score=adm_parameters["score_wikipedia"],
        )
    ]
