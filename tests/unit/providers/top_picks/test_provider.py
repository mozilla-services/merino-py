# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the top picks provider module."""

import time
from collections import defaultdict

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture

from merino.configs.config import settings
from merino.exceptions import BackendError
from merino.providers.base import BaseSuggestion, Category
from merino.providers.top_picks.backends.filemanager import GetFileResultCode
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider, Suggestion
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture

# NOTE: top_picks provider fixture in conftest.py.


@pytest.fixture(name="expected_empty_top_picks_data")
def fixture_expected_empty_top_picks_data() -> TopPicksData:
    """Fixture for empty default TopPicksData class."""
    return TopPicksData(
        primary_index=defaultdict(),
        secondary_index=defaultdict(),
        short_domain_index=defaultdict(),
        results=[],
        query_min=0,
        query_max=0,
        query_char_limit=0,
        firefox_char_limit=0,
    )


def test_enabled_by_default(top_picks: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert top_picks.enabled_by_default is True


def test_hidden(top_picks: Provider) -> None:
    """Test for the hidden method."""
    assert top_picks.hidden() is False


@pytest.mark.asyncio
async def test_initialize(top_picks: Provider, backend: TopPicksBackend) -> None:
    """Test initialization of top pick provider"""
    await top_picks.initialize()

    result_code, backend_data = await backend.fetch()

    assert result_code is GetFileResultCode.SUCCESS
    assert top_picks.top_picks_data == backend_data
    assert top_picks.last_fetch_at > 0


@pytest.mark.asyncio
async def test_initialize_skip(
    mocker,
    top_picks: Provider,
    backend: TopPicksBackend,
    expected_empty_top_picks_data: TopPicksData,
) -> None:
    """Test initialization of top pick provider when result_code enum value is skip"""
    mocker.patch(
        "merino.configs.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"
    mocker.patch(
        "merino.providers.top_picks.backends.top_picks.TopPicksBackend.fetch"
    ).return_value = (GetFileResultCode.SKIP, None)
    await top_picks.initialize()

    assert top_picks.top_picks_data == expected_empty_top_picks_data


@pytest.mark.asyncio
async def test_initialize_fail(
    mocker,
    top_picks: Provider,
    backend: TopPicksBackend,
    expected_empty_top_picks_data: TopPicksData,
) -> None:
    """Test initialization of top pick provider when result_code enum value is fail"""
    mocker.patch(
        "merino.configs.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"
    mocker.patch(
        "merino.providers.top_picks.backends.top_picks.TopPicksBackend.fetch"
    ).return_value = (GetFileResultCode.FAIL, None)
    await top_picks.initialize()

    assert top_picks.top_picks_data == expected_empty_top_picks_data


def test_should_fetch_true(top_picks: Provider):
    """Test that provider should fetch is true."""
    top_picks.last_fetch_at = time.time() - top_picks.resync_interval_sec - 100
    assert top_picks._should_fetch()


def test_should_fetch_false(top_picks: Provider):
    """Test that provider should fetch is false."""
    top_picks.last_fetch_at = time.time()
    assert top_picks._should_fetch() is False


@pytest.mark.asyncio
async def test_fetch_top_picks_data(top_picks: Provider):
    """Test that the _fetch_top_picks_data returns TopPicksData."""
    await top_picks._fetch_top_picks_data()
    assert top_picks.top_picks_data
    assert top_picks.last_fetch_at > 0


@pytest.mark.asyncio
async def test_fetch_top_picks_data_fails(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend: TopPicksBackend,
    top_picks: Provider,
    mocker,
):
    """Test that the _fetch_top_picks_data fails as expected."""
    mocker.patch.object(backend, "fetch", side_effect=BackendError())

    await top_picks._fetch_top_picks_data()

    records = filter_caplog(caplog.records, "merino.providers.top_picks.provider")
    assert len(records) == 1


@pytest.mark.asyncio
async def test_fetch_top_picks_data_skip(
    mocker,
    top_picks: Provider,
    backend: TopPicksBackend,
    expected_empty_top_picks_data: TopPicksData,
) -> None:
    """Test _fetch_top_picks_data_skip when result_code enum value is skip."""
    mocker.patch(
        "merino.configs.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"
    mocker.patch(
        "merino.providers.top_picks.backends.top_picks.TopPicksBackend.fetch"
    ).return_value = (GetFileResultCode.SKIP, None)
    await top_picks._fetch_top_picks_data()

    assert top_picks.top_picks_data == expected_empty_top_picks_data


@pytest.mark.asyncio
async def test_fetch_top_picks_data_fail(
    mocker,
    top_picks: Provider,
    backend: TopPicksBackend,
    expected_empty_top_picks_data: TopPicksData,
) -> None:
    """Test _fetch_top_picks_data_skip when result_code enum value is fail."""
    mocker.patch(
        "merino.configs.config.settings.providers.top_picks.domain_data_source"
    ).return_value = "remote"
    mocker.patch(
        "merino.providers.top_picks.backends.top_picks.TopPicksBackend.fetch"
    ).return_value = (GetFileResultCode.FAIL, None)

    await top_picks._fetch_top_picks_data()

    assert top_picks.top_picks_data == expected_empty_top_picks_data


@pytest.mark.parametrize(
    ["query", "expected"],
    [
        ("example", "example"),
        ("EXAMPLE", "example"),
        ("ExAmPlE", "example"),
        ("example ", "example"),
        (" example ", "example"),
        ("  example", "example"),
        ("example   ", "example"),
        ("   example   ", "example"),
    ],
    ids=[
        "normalized",
        "uppercase",
        "mixed-case",
        "tail space",
        "leading space",
        "multi-leading space",
        "multi-tail space",
        "leading and trailing space",
    ],
)
def test_normalize_query(top_picks: Provider, query: str, expected: str) -> None:
    """Test for the query normalization method to strip trailing space and
    convert to lowercase.
    """
    assert top_picks.normalize_query(query) == expected


@pytest.mark.asyncio
async def test_initialize_failure(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend: TopPicksBackend,
    top_picks: Provider,
    mocker,
) -> None:
    """Test exception handling for the initialize() method."""
    error_message: str = "Failed to fetch data from Top Picks Backend."
    # override default behavior for fetch
    mocker.patch.object(backend, "fetch", side_effect=BackendError(error_message))

    await top_picks.initialize()

    records = filter_caplog(caplog.records, "merino.providers.top_picks.provider")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == error_message


@pytest.mark.parametrize(
    ["query", "title", "url"],
    [
        ("exam", "Example", "https://example.com"),
        ("exxamp", "Example", "https://example.com"),
        ("example", "Example", "https://example.com"),
    ],
)
@pytest.mark.asyncio
async def test_query(
    srequest: SuggestionRequestFixture,
    top_picks: Provider,
    query: str,
    title: str,
    url: str,
) -> None:
    """Test for the query method of the Top Pick provider. Includes testing for query
    normalization, when uppercase or trailing whitespace in query string.
    """
    await top_picks.initialize()

    result: list[BaseSuggestion] = await top_picks.query(srequest(query))
    assert result == [
        Suggestion(
            block_id=0,
            title=title,
            url=HttpUrl(url),
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
            categories=[Category.Inconclusive],
        )
    ]


@pytest.mark.asyncio
async def test_query_with_top_pick_without_category(
    srequest: SuggestionRequestFixture,
    top_picks: Provider,
) -> None:
    """Test for the query method of the Top Pick provider. Includes testing for query
    normalization, when uppercase or trailing whitespace in query string.
    """
    await top_picks.initialize()
    query = "pine"
    result: list[BaseSuggestion] = await top_picks.query(srequest(query))
    assert result == [
        Suggestion(
            block_id=0,
            title="Pineapple",
            url=HttpUrl("https://pineapple.test"),
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]


@pytest.mark.parametrize(
    "query",
    [
        "am",
        "https://",
        "supercalifragilisticexpialidocious",
    ],
)
@pytest.mark.asyncio
async def test_query_filtered_input(
    srequest: SuggestionRequestFixture,
    top_picks: Provider,
    query: str,
) -> None:
    """Test for filtering logic of the query method in the Top Pick provider
    to not return results when given a query string that is invalid.
    """
    await top_picks.initialize()

    assert await top_picks.query(srequest(query)) == []


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
            url=HttpUrl(url),
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
            categories=[Category.Inconclusive],
        )
    ]
    await top_picks.initialize()

    result = await top_picks.query(srequest(query))
    assert result == expected_suggestion


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

    result = await top_picks.query(srequest(query))
    assert result == []


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
            url=HttpUrl(url),
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
            categories=[Category.Inconclusive],
        )
    ]
    await top_picks.initialize()

    result = await top_picks.query(srequest(query))
    assert result == expected_suggestion
