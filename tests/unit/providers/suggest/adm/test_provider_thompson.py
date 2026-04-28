# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Thompson sampling code path of the AdM provider."""

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import HttpUrl

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.optimizers.thompson import ThompsonSampler
from merino.providers.suggest.adm.backends.protocol import (
    KeywordEngagementData,
    KeywordEntry,
    KeywordMetrics,
)
from merino.providers.suggest.adm.provider import NonsponsoredSuggestion, Provider

from tests.unit.types import SuggestionRequestFixture

GEOLOCATION = Location(country="US")
USER_AGENT = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")


CLIENT_VARIANTS: list[str] = ["engagement_guided_suggestions"]


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
    statsd_mock: Any,
) -> None:
    """Thompson-enabled provider should return a suggestion when the sampler picks a winner."""
    await adm_with_thompson.initialize()
    res = await adm_with_thompson.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
    statsd_mock.increment.assert_called_once_with(
        "providers.adm.thompson.select", tags={"outcome": "selected", "subject": "example.org"}
    )


@pytest.mark.asyncio
async def test_query_with_thompson_dummy_suppresses_suggestion(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_dummy: Provider,
    statsd_mock: Any,
) -> None:
    """Provider with a dominant dummy should suppress the suggestion (return empty list)."""
    await adm_with_thompson_dummy.initialize()
    adm_with_thompson_dummy.keyword_engagement_data = KeywordEngagementData(
        amp={"something": KeywordEntry(historical=KeywordMetrics(impressions=1, clicks=0))},
        amp_aggregated={},
    )

    res = await adm_with_thompson_dummy.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

    assert res == []
    statsd_mock.increment.assert_called_once_with(
        "providers.adm.thompson.select", tags={"outcome": "suppressed", "subject": "example.org"}
    )


@pytest.mark.asyncio
async def test_query_with_thompson_no_match_returns_empty(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
) -> None:
    """Thompson-enabled provider should return empty list when the query matches nothing."""
    await adm_with_thompson.initialize()
    client_variants = CLIENT_VARIANTS

    res = await adm_with_thompson.query(srequest("zzznomatch", None, None, client_variants))

    assert res == []


@pytest.mark.asyncio
async def test_query_with_thompson_uses_fallback_country_and_form_factor(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """Thompson-enabled provider should apply country/form-factor fallbacks when absent."""
    await adm_with_thompson.initialize()
    client_variants = CLIENT_VARIANTS
    res = await adm_with_thompson.query(srequest("firefox", None, None, client_variants))

    assert len(res) == 1
    assert res[0].score == adm_parameters["score"]


@pytest.mark.asyncio
async def test_query_with_thompson_min_attempted_count_returns_suggestion(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_dummy_min_attempted_count: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """Thompson-enabled provider should return a suggestion when the only candidate's
    attempted count is below the minimal attempted count.
    """
    await adm_with_thompson_dummy_min_attempted_count.initialize()

    res = await adm_with_thompson_dummy_min_attempted_count.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
async def test_query_with_thompson_without_client_variants_check(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_skip_client_variants_check: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """Thompson-enabled provider without the client_variants check should return
    a suggestion when the sampler picks a winner even if client_variants does
    not match.
    """
    await adm_with_thompson_skip_client_variants_check.initialize()
    client_variants: list[str] = []
    res = await adm_with_thompson_skip_client_variants_check.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, client_variants)
    )

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
async def test_query_with_thompson_single_candidate_below_threshold_returns_suggestion(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_single_candidate_below_threshold: Provider,
    adm_parameters: dict[str, Any],
    statsd_mock: Any,
) -> None:
    """Single candidate below min_attempted_count should bypass sampling, return the suggestion,
    and emit the 'skipped' outcome metric.
    """
    await adm_with_thompson_single_candidate_below_threshold.initialize()
    res = await adm_with_thompson_single_candidate_below_threshold.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
    statsd_mock.increment.assert_called_once_with(
        "providers.adm.thompson.select", tags={"outcome": "skipped", "subject": "example.org"}
    )


@pytest.mark.asyncio
async def test_query_with_thompson_without_engagement_data_skips_sampling(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_dummy: Provider,
    adm_parameters: dict[str, Any],
    statsd_mock: Any,
) -> None:
    """Provider should skip Thompson sampling when engagement data is empty."""
    await adm_with_thompson_dummy.initialize()

    res = await adm_with_thompson_dummy.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
    statsd_mock.increment.assert_not_called()


@patch("merino.providers.suggest.adm.provider.TS_DRY_RUN", True)
@pytest.mark.asyncio
async def test_query_with_thompson_returns_fallback_when_fallback_enabled(
    srequest: SuggestionRequestFixture,
    adm_with_thompson: Provider,
    adm_parameters: dict[str, Any],
    statsd_mock: Any,
) -> None:
    """Thompson-enabled provider should return fallback when TS_DRY_RUN is enabled."""
    await adm_with_thompson.initialize()
    res = await adm_with_thompson.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
    statsd_mock.increment.assert_called_once_with(
        "providers.adm.thompson.select", tags={"outcome": "selected", "subject": "example.org"}
    )


@patch("merino.providers.suggest.adm.provider.TS_DRY_RUN", True)
@pytest.mark.asyncio
async def test_query_with_thompson_dummy_return_suggestion_when_fallback_enabled(
    srequest: SuggestionRequestFixture,
    adm_with_thompson_dummy: Provider,
    adm_parameters: dict[str, Any],
    statsd_mock: Any,
) -> None:
    """Provider with a dominant dummy should return fallback suggestion when TS_DRY_RUN is enabled."""
    await adm_with_thompson_dummy.initialize()
    adm_with_thompson_dummy.keyword_engagement_data = KeywordEngagementData(
        amp={"something": KeywordEntry(historical=KeywordMetrics(impressions=1, clicks=0))},
        amp_aggregated={},
    )

    res = await adm_with_thompson_dummy.query(
        srequest("firefox", GEOLOCATION, USER_AGENT, CLIENT_VARIANTS)
    )

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
    statsd_mock.increment.assert_called_once_with(
        "providers.adm.thompson.select", tags={"outcome": "suppressed", "subject": "example.org"}
    )
