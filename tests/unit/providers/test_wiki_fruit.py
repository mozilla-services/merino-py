# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wiki Fruit provider module."""

import pytest
from fastapi import APIRouter, FastAPI

from merino.providers.base import BaseSuggestion
from merino.providers.wiki_fruit import Suggestion, WikiFruitProvider
from tests.unit.types import SuggestionRequestFixture

app = FastAPI()
router = APIRouter()


@pytest.fixture(name="wiki_fruit")
def fixture_wiki_fruit() -> WikiFruitProvider:
    """Return Top Pick Navigational Query Provider"""
    return WikiFruitProvider("wiki_fruit", False)


def test_enabled_by_default(wiki_fruit: WikiFruitProvider) -> None:
    """Test for the enabled_by_default method."""
    assert wiki_fruit.enabled_by_default is False


def test_hidden(wiki_fruit: WikiFruitProvider) -> None:
    """Test for the hidden method."""
    assert wiki_fruit.hidden() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["nope"])
async def test_query_no_suggestion(
    srequest: SuggestionRequestFixture, wiki_fruit: WikiFruitProvider, query: str
) -> None:
    """Test for the return of no suggestions when invalid query term provided to
    query method of the Wiki Fruit provider.
    """
    await wiki_fruit.initialize()

    result: list[BaseSuggestion] = await wiki_fruit.query(srequest(query))
    assert result == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["apple", "banana", "cherry"])
async def test_query_suggestion(
    srequest: SuggestionRequestFixture, wiki_fruit: WikiFruitProvider, query: str
) -> None:
    """Test for successful return of a suggestion for query method of the Wiki Fruit provider."""
    await wiki_fruit.initialize()

    result: list[BaseSuggestion] = await wiki_fruit.query(srequest(query))
    assert result == [
        Suggestion(
            block_id=1,
            full_keyword=query,
            title=f"Wikipedia - {query.capitalize()}",
            url=f"https://en.wikipedia.org/wiki/{query.capitalize()}",
            impression_url="https://127.0.0.1/",
            click_url="https://127.0.0.1/",
            provider="wiki_fruit",
            advertiser="test_advertiser",
            is_sponsored=False,
            icon="https://en.wikipedia.org/favicon.ico",
            score=0,
        )
    ]
