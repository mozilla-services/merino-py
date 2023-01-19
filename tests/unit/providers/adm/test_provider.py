# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm provider module."""

from typing import Any

import pytest
from pytest import LogCaptureFixture

from merino.providers.adm.backends.protocol import Content
from merino.providers.adm.provider import NonsponsoredSuggestion, Provider
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture


def test_enabled_by_default(adm: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert adm.enabled_by_default is True


def test_hidden(adm: Provider) -> None:
    """Test for the hidden method."""
    assert adm.hidden() is False


@pytest.mark.asyncio
async def test_initialize(adm: Provider, adm_suggestion_content: Content) -> None:
    """Test for the initialize() method of the adM provider."""
    await adm.initialize()

    assert adm.content == adm_suggestion_content
    assert adm.last_fetch_at > 0


@pytest.mark.asyncio
async def test_initialize_remote_settings_failure(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    backend_mock: Any,
    adm: Provider,
) -> None:
    """Test exception handling for the initialize() method."""
    error_message: str = "The remote server was unreachable"
    # override default mocked behavior for fetch
    backend_mock.fetch.side_effect = Exception(error_message)

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
async def test_query_success(
    srequest: SuggestionRequestFixture, adm: Provider, adm_parameters: dict[str, Any]
) -> None:
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
            score=adm_parameters["score"],
        )
    ]


@pytest.mark.asyncio
async def test_query_with_missing_key(
    srequest: SuggestionRequestFixture, adm: Provider
) -> None:
    """Test for the query() method of the adM provider with a missing key."""
    await adm.initialize()

    assert await adm.query(srequest("nope")) == []
