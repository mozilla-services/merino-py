# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the top picks provider module."""
from typing import Any

import pytest
from pytest import LogCaptureFixture

from merino.config import settings
from merino.providers.base import BaseSuggestion
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.provider import Provider, Suggestion
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture

configs = settings.providers.top_picks
# NOTE: top_picks provider fixture in conftest.py.

top_picks_example = {
    "domains": [
        {
            "title": "Mozilla",
            "url": "https://mozilla.org/en-US/",
            "icon": "",
            "categories": ["web-browser"],
            "similars": ["mozzilla", "mozila"],
        },
    ]
}


def test_enabled_by_default(top_picks: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert top_picks.enabled_by_default is True


def test_hidden(top_picks: Provider) -> None:
    """Test for the hidden method."""
    assert top_picks.hidden() is False


@pytest.mark.asyncio
async def test_initialize(top_picks: Provider, top_picks_data: TopPicksData) -> None:
    """Test initialization of top pick provider"""
    await top_picks.initialize()

    assert top_picks.top_picks_data == top_picks_data


@pytest.mark.asyncio
async def test_initialize_exception(top_picks: Provider, mocker) -> None:
    """Test that exception is thrown if initialization is unsuccessful."""
    mocker.patch.object(top_picks, "initialize", side_effect=Exception)
    with pytest.raises(Exception):
        await top_picks.initialize()


@pytest.mark.asyncio
async def test_initialize_failure(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend_mock: Any,
    top_picks: Provider,
) -> None:
    """Test exception handling for the initialize() method."""
    error_message: str = "Failed to fetch data from Top Picks Backend."
    # override default mocked behavior for fetch
    backend_mock.fetch.side_effect = Exception(error_message)

    await top_picks.initialize()

    records = filter_caplog(caplog.records, "merino.providers.top_picks.provider")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == error_message


@pytest.mark.asyncio
async def test_query(srequest: SuggestionRequestFixture, top_picks: Provider) -> None:
    """Test for the query method of the Top Pick provider."""
    await top_picks.initialize()

    assert await top_picks.query(srequest("am")) == []
    assert await top_picks.query(srequest("https://")) == []
    assert await top_picks.query(srequest("supercalifragilisticexpialidocious")) == []

    result: list[BaseSuggestion] = await top_picks.query(srequest("example"))
    assert result == [
        Suggestion(
            block_id=0,
            title="Example",
            url="https://example.com",
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]

    result = await top_picks.query(srequest("exxamp"))
    assert result == [
        Suggestion(
            block_id=0,
            title="Example",
            url="https://example.com",
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]


@pytest.mark.parametrize(
    ["query", "title", "url"],
    [
        ("aa", "Abc", "https://abc.test"),
        ("ab", "Abc", "https://abc.test"),
        ("abc", "Abc", "https://abc.test"),
    ],
)
@pytest.mark.asyncio
async def test_short_domain_query(
    query, title, url, srequest: SuggestionRequestFixture, top_picks: Provider
) -> None:
    """Test the Top Pick Provider returns results for short domain queries.
    Ensure that matching suggestion and similar variants with low char
    threshold return suggestions.
    """
    expected_suggestion: list[Suggestion] = [
        Suggestion(
            block_id=0,
            title=title,
            url=url,
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]
    await top_picks.initialize()

    res = await top_picks.query(srequest(query))
    assert res == expected_suggestion


@pytest.mark.parametrize(
    "query",
    ["a", "ad", "bb"],
)
@pytest.mark.asyncio
async def test_short_domain_query_fails(
    query, srequest: SuggestionRequestFixture, top_picks: Provider
) -> None:
    """Test invalid inputs for Top Pick Provider when providing short domain queries."""
    await top_picks.initialize()

    res = await top_picks.query(srequest(query))
    assert res == []


@pytest.mark.parametrize(
    ["query", "title", "url"],
    [
        ("ac", "Abc", "https://abc.test"),
        ("acb", "Abc", "https://abc.test"),
        ("acbc", "Abc", "https://abc.test"),
        ("aecbc", "Abc", "https://abc.test"),
    ],
)
@pytest.mark.asyncio
async def test_short_domain_query_similars_longer_than_domain(
    query, title, url, srequest: SuggestionRequestFixture, top_picks: Provider
) -> None:
    """Test suggestion results for similar inputs that are indexed for short domains.
    These similar suggestion results may be longer than the input, so if the domain is
    categorized as short and the similar is longer than it, the result should
    still return a valid suggestion as its characters will be a subset of the similar.
    """
    expected_suggestion: list[Suggestion] = [
        Suggestion(
            block_id=0,
            title=title,
            url=url,
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]
    await top_picks.initialize()

    res = await top_picks.query(srequest(query))
    assert res == expected_suggestion
