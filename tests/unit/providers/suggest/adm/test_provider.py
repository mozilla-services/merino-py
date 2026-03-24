# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm provider module."""

from typing import Any

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.providers.suggest.adm.backends.protocol import EngagementData, FormFactor
from merino.providers.suggest.adm.provider import NonsponsoredSuggestion, Provider

from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture


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

    assert adm.suggestion_content.index_manager.stats(f"US/({FormFactor.DESKTOP.value},)") == {
        "keyword_index_size": 5,
        "suggestions_count": 1,
        "icons_count": 1,
        "advertisers_count": 1,
        "url_templates_count": 1,
    }
    assert adm.suggestion_content.index_manager.stats(f"DE/({FormFactor.PHONE.value},)") == {
        "keyword_index_size": 7,
        "advertisers_count": 1,
        "icons_count": 1,
        "suggestions_count": 1,
        "url_templates_count": 1,
    }
    assert adm.last_fetch_at > 0


@pytest.mark.parametrize(
    ["query", "expected"],
    [
        ("example", "example"),
        ("EXAMPLE", "example"),
        ("ExAmPlE", "example"),
        ("example ", "example "),
        (" example ", "example "),
        ("  example", "example"),
        ("example  ", "example  "),
        ("   example   ", "example   "),
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
        # Clean up the cron tasks. Unlike other test cases, this action is necessary here
        # since the cron jobs have kicked in as the initial fetch fails.
        adm.cron_task.cancel()
        adm.engagement_cron_task.cancel()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.provider")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == error_message
    assert adm.last_fetch_at == 0
    # SuggestionContent should be empty as initialize was unsuccessful.
    assert adm.suggestion_content.index_manager.list() == []
    assert adm.suggestion_content.icons == {}
    assert await adm.query(srequest(query, None, None)) == []


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
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")
    res = await adm.query(srequest(query, geolocation, user_agent))
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


@pytest.mark.parametrize("query", ["firefox"])
@pytest.mark.asyncio
async def test_query_with_missing_key(
    srequest: SuggestionRequestFixture,
    adm: Provider,
    query: str,
    adm_parameters: dict[str, Any],
) -> None:
    """Test for the query() method of the adM provider with missing keys, the fallback should be used"""
    await adm.initialize()

    res = await adm.query(srequest(query, None, None))
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


SAMPLE_ENGAGEMENT_DATA = EngagementData(
    amp={
        "1-800 flowers": {"advertiser": "1-800 flowers", "impressions": 2803, "clicks": 10},
        "aliexpress": {"advertiser": "aliexpress", "impressions": 1449, "clicks": 102},
    },
    amp_aggregated={"impressions": 463225, "clicks": 5878},
)


@pytest.mark.asyncio
async def test_fetch_engagement_data_success(
    mocker: MockerFixture,
    adm: Provider,
) -> None:
    """Test that _fetch_engagement_data stores data and updates the timestamp on success."""
    mocker.patch.object(adm.filemanager, "get_file", return_value=SAMPLE_ENGAGEMENT_DATA)

    assert adm.last_engagement_fetch_at == 0
    await adm._fetch_engagement_data()

    assert adm.engagement_data == SAMPLE_ENGAGEMENT_DATA
    assert adm.last_engagement_fetch_at > 0


@pytest.mark.asyncio
async def test_fetch_engagement_data_returns_none(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    adm: Provider,
) -> None:
    """Test that a None return from get_file logs a warning and does not update the timestamp,
    so the cron retries on the next tick.
    """
    mocker.patch.object(adm.filemanager, "get_file", return_value=None)
    original_data = adm.engagement_data

    await adm._fetch_engagement_data()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.provider")
    assert len(records) == 1
    assert "None" in records[0].message
    assert adm.engagement_data == original_data
    assert adm.last_engagement_fetch_at == 0


@pytest.mark.asyncio
async def test_fetch_engagement_data_exception(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    adm: Provider,
) -> None:
    """Test that an exception from get_file logs a warning and does not update the timestamp."""
    mocker.patch.object(adm.filemanager, "get_file", side_effect=Exception("GCS unavailable"))
    original_data = adm.engagement_data

    await adm._fetch_engagement_data()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.provider")
    assert len(records) == 1
    assert records[0].__dict__["error"] == "GCS unavailable"
    assert adm.engagement_data == original_data
    assert adm.last_engagement_fetch_at == 0
