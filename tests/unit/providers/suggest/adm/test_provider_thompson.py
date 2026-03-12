# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Thompson sampling code path of the AdM provider."""

from typing import Any

import pytest
from pydantic import HttpUrl

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.optimizers.thompson import ThompsonSampler
from merino.providers.suggest.adm.provider import NonsponsoredSuggestion, Provider

from tests.unit.types import SuggestionRequestFixture


def test_thompson_attribute_is_none_by_default(adm: Provider) -> None:
    """Provider created without a thompson argument should have thompson=None."""
    assert adm.thompson is None


def test_thompson_attribute_is_set(adm_with_thompson: Provider) -> None:
    """Provider created with a ThompsonSampler should expose it on the attribute."""
    assert isinstance(adm_with_thompson.thompson, ThompsonSampler)


@pytest.mark.asyncio
async def test_query_with_thompson_returns_suggestion(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """Thompson-enabled provider should return a suggestion when the sampler picks a winner."""
    await adm_with_thompson.initialize()
    geolocation = Location(country="US")
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")

    res = await adm_with_thompson.query(srequest("firefox", geolocation, user_agent))

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
async def test_query_with_thompson_dummy_suppresses_suggestion(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_dummy: Provider,
) -> None:
    """Provider with a dominant dummy should suppress the suggestion (return empty list)."""
    await adm_with_thompson_dummy.initialize()
    geolocation = Location(country="US")
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")

    res = await adm_with_thompson_dummy.query(srequest("firefox", geolocation, user_agent))

    assert res == []


@pytest.mark.asyncio
async def test_query_with_thompson_no_match_returns_empty(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
) -> None:
    """Thompson-enabled provider should return empty list when the query matches nothing."""
    await adm_with_thompson.initialize()

    res = await adm_with_thompson.query(srequest("zzznomatch", None, None))

    assert res == []


@pytest.mark.asyncio
async def test_query_with_thompson_uses_fallback_country_and_form_factor(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """Thompson-enabled provider should apply country/form-factor fallbacks when absent."""
    await adm_with_thompson.initialize()

    res = await adm_with_thompson.query(srequest("firefox", None, None))

    assert len(res) == 1
    assert res[0].score == adm_parameters["score"]
