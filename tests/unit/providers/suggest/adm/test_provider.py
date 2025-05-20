# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm provider module."""

from typing import Any

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture

from merino.providers.suggest.adm.backends.protocol import SuggestionContent
from merino.providers.suggest.adm.provider import NonsponsoredSuggestion, Provider
from merino.providers.suggest.base import Category
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture


def test_enabled_by_default(adm: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert adm.enabled_by_default is True


def test_hidden(adm: Provider) -> None:
    """Test for the hidden method."""
    assert adm.hidden() is False


@pytest.mark.asyncio
async def test_initialize(adm: Provider, adm_suggestion_content: SuggestionContent) -> None:
    """Test for the initialize() method of the adM provider."""
    await adm.initialize()

    assert adm.suggestion_content == adm_suggestion_content
    assert adm.last_fetch_at > 0


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
def test_normalize_query(adm: Provider, query: str, expected: str) -> None:
    """Test for the query normalization method to strip trailing space and
    convert to lowercase.
    """
    assert adm.normalize_query(query) == expected


@pytest.mark.parametrize("query", ["firefox"])
@pytest.mark.asyncio
async def test_initialize_remote_settings_failure(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend_mock: Any,
    adm: Provider,
    srequest: SuggestionRequestFixture,
    query,
) -> None:
    """Test exception handling for the initialize() method and querying
    of provider to return an empty suggestion.
    """
    error_message: str = "The remote server was unreachable"
    # override default mocked behavior for fetch
    backend_mock.fetch.side_effect = Exception(error_message)

    try:
        await adm.initialize()
    finally:
        # Clean up the cron task. Unlike other test cases, this action is necessary here
        # since the cron job has kicked in as the initial fetch fails.
        adm.cron_task.cancel()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.provider")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == error_message
    assert adm.last_fetch_at == 0
    # SuggestionContent should be empty as initialize was unsuccessful.
    assert adm.suggestion_content == SuggestionContent(
        suggestions={},
        full_keywords=[],
        results=[],
        icons={},
    )
    assert await adm.query(srequest(query)) == []


@pytest.mark.parametrize("query", ["firefox"])
@pytest.mark.asyncio
async def test_query_success(
    srequest: SuggestionRequestFixture,
    adm: Provider,
    adm_parameters: dict[str, Any],
    query: str,
) -> None:
    """Test for the query() method of the adM provider.  Includes testing for query
    normalization, when uppercase or trailing whitespace in query string.
    """
    await adm.initialize()

    res = await adm.query(srequest(query))
    assert res == [
        NonsponsoredSuggestion(
            block_id=2,
            full_keyword="firefox accounts",
            title="Mozilla Firefox Accounts",
            url=HttpUrl("https://example.org/target/mozfirefoxaccounts"),
            categories=[],
            impression_url=HttpUrl("https://example.org/impression/mozilla"),
            click_url=HttpUrl("https://example.org/click/mozilla"),
            provider="adm",
            advertiser="Example.org",
            is_sponsored=False,
            icon="attachment-host/main-workspace/quicksuggest/icon-01",
            score=adm_parameters["score"],
        )
    ]


@pytest.mark.asyncio
async def test_query_with_missing_key(srequest: SuggestionRequestFixture, adm: Provider) -> None:
    """Test for the query() method of the adM provider with a missing key."""
    await adm.initialize()

    assert await adm.query(srequest("nope")) == []


@pytest.mark.parametrize(
    ["domain", "expected"],
    [
        ("testserpcategories.com", [Category.Education]),
        ("nocategories.com", []),
    ],
)
@pytest.mark.asyncio
async def test_query_serp_categories(adm: Provider, domain: str, expected: list[Category]) -> None:
    """Test for the serp_categories() method of the adM provider."""
    categories = adm.serp_categories(domain)

    assert categories == expected
