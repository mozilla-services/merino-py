# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the adm provider module."""

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.providers.suggest.adm.backends.protocol import (
    FormFactor,
    EngagementData,
    KeywordEntry,
    KeywordMetrics,
)
from merino.providers.suggest.adm.fuzzy import RejectionReason
from merino.providers.suggest.adm.provider import (
    AMP_FUZZY_VARIANT,
    NonsponsoredSuggestion,
    Provider,
)

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
        "full_keywords_count": 2,
        "fuzzy_keywords_count": 2,
        "fuzzy_delete_index_size": 39,
    }
    assert adm.suggestion_content.index_manager.stats(f"DE/({FormFactor.PHONE.value},)") == {
        "keyword_index_size": 7,
        "advertisers_count": 1,
        "icons_count": 1,
        "suggestions_count": 1,
        "url_templates_count": 1,
        "full_keywords_count": 2,
        "fuzzy_keywords_count": 2,
        "fuzzy_delete_index_size": 45,
    }
    assert adm.last_fetch_at > 0


@pytest.mark.asyncio
async def test_full_keywords_returns_indexed_full_keywords(adm: Provider) -> None:
    """`full_keywords()` returns the distinct full keywords indexed for a segment.

    These are the terms the ED1 fuzzy index is built from (and the source for the
    AMP slice of the query-normalization canonical). For the `firefox accounts`
    fixture record they are exactly its two `full_keywords` entries.
    """
    await adm.initialize()

    assert sorted(
        adm.suggestion_content.index_manager.full_keywords(f"US/({FormFactor.DESKTOP.value},)")
    ) == ["firefox accounts", "mozilla firefox accounts"]


@pytest.mark.asyncio
async def test_fuzzy_rescues_single_typo(adm: Provider) -> None:
    """A single-typo query misses with fuzzy off and is rescued with fuzzy on.

    `firefox accountz` is one substitution from the full keyword `firefox accounts`:
    exact/prefix lookup misses it, while the ED1 fuzzy fallback recovers it and flags
    the result `matched_via == "fuzzy"`.
    """
    await adm.initialize()
    idx_id = f"US/({FormFactor.DESKTOP.value},)"
    index_manager = adm.suggestion_content.index_manager

    # fuzzy off: the typo is not a prefix of any keyword -> no match
    assert index_manager.query(idx_id, "firefox accountz", fuzzy=False) == []

    # fuzzy on: rescued to the nearest full keyword, flagged as a fuzzy match
    rescued = index_manager.query(idx_id, "firefox accountz", fuzzy=True)
    assert len(rescued) == 1
    assert rescued[0].matched_via == "fuzzy"
    assert rescued[0].full_keyword == "firefox accounts"
    assert rescued[0].advertiser == "Example.org"


@pytest.mark.parametrize(
    "client_variants",
    [None, [], ["some_other_variant"]],
    ids=["no-variants", "empty-variants", "other-variant"],
)
@pytest.mark.asyncio
async def test_query_no_fuzzy_without_treatment_variant(
    srequest: SuggestionRequestFixture,
    adm: Provider,
    client_variants: list[str] | None,
) -> None:
    """Without the treatment variant the fuzzy fallback stays off, so a typo returns nothing."""
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    res = await adm.query(srequest("firefox accountz", geolocation, user_agent, client_variants))

    assert res == []


@pytest.mark.asyncio
async def test_query_fuzzy_rescues_typo_for_treatment(
    srequest: SuggestionRequestFixture,
    adm: Provider,
    adm_parameters: dict[str, Any],
) -> None:
    """With the treatment variant, a single-typo miss is rescued to its AMP suggestion."""
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    res = await adm.query(
        srequest("firefox accountz", geolocation, user_agent, [AMP_FUZZY_VARIANT])
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
async def test_query_fuzzy_drops_guardrail_rejected_candidate(
    srequest: SuggestionRequestFixture,
    adm: Provider,
) -> None:
    """A fuzzy candidate that fails a guardrail (first-char substitution) is dropped."""
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    # "girefox accounts" is a first-char substitution of "firefox accounts": the extension
    # surfaces it as a fuzzy candidate, but the guardrail rejects it as too risky.
    res = await adm.query(
        srequest("girefox accounts", geolocation, user_agent, [AMP_FUZZY_VARIANT])
    )

    assert res == []


@pytest.mark.asyncio
async def test_query_fuzzy_variant_leaves_exact_match_unchanged(
    srequest: SuggestionRequestFixture,
    adm: Provider,
) -> None:
    """The treatment variant does not disturb exact/prefix matches."""
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    res = await adm.query(srequest("firefox", geolocation, user_agent, [AMP_FUZZY_VARIANT]))

    assert len(res) == 1
    suggestion = res[0]
    assert isinstance(suggestion, NonsponsoredSuggestion)
    assert suggestion.full_keyword == "firefox accounts"


@pytest.mark.asyncio
async def test_query_fuzzy_emits_metrics(
    srequest: SuggestionRequestFixture,
    adm: Provider,
    statsd_mock: Any,
) -> None:
    """Fuzzy serving emits candidate_found + served on a rescue, and candidate_found +
    rejected(reason) + miss when every candidate is guardrail-rejected.
    """
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    # rescue -> candidate found and served
    await adm.query(srequest("firefox accountz", geolocation, user_agent, [AMP_FUZZY_VARIANT]))
    statsd_mock.increment.assert_any_call("providers.adm.fuzzy.candidate_found")
    statsd_mock.increment.assert_any_call("providers.adm.fuzzy.served")

    statsd_mock.increment.reset_mock()

    # guardrail drop -> candidate found, rejected with reason, and overall miss
    await adm.query(srequest("girefox accounts", geolocation, user_agent, [AMP_FUZZY_VARIANT]))
    statsd_mock.increment.assert_any_call("providers.adm.fuzzy.candidate_found")
    statsd_mock.increment.assert_any_call(
        "providers.adm.fuzzy.rejected",
        tags={"reason": RejectionReason.FIRST_CHAR_SUBSTITUTION},
    )
    statsd_mock.increment.assert_any_call("providers.adm.fuzzy.miss")


@patch("merino.providers.suggest.adm.provider.AMP_FUZZY_ENABLED", False)
@pytest.mark.asyncio
async def test_query_fuzzy_disabled_by_kill_switch(
    srequest: SuggestionRequestFixture,
    adm: Provider,
) -> None:
    """With the kill-switch off, the treatment variant no longer enables the fuzzy fallback."""
    await adm.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    res = await adm.query(
        srequest("firefox accountz", geolocation, user_agent, [AMP_FUZZY_VARIANT])
    )

    assert res == []


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
    error_message_engagement: str = "Engagement data fetch returned None, will retry on next tick"
    # override default mocked behavior for fetch
    backend_mock.fetch.side_effect = Exception(error_message)

    try:
        await adm.initialize()
    finally:
        # Clean up the cron tasks. Unlike other test cases, this action is necessary here
        # since the cron jobs have kicked in as the initial fetch fails.
        adm.cron_task.cancel()
        adm.engagement_cron_task.cancel()
        adm.staleness_cron_task.cancel()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.provider")
    assert len(records) == 2
    assert records[0].__dict__["error message"] == error_message
    assert adm.last_fetch_at == 0
    assert records[1].message == error_message_engagement
    # SuggestionContent should be empty as initialize was unsuccessful.
    assert adm.suggestion_content.index_manager.list() == []
    assert adm.suggestion_content.icons == {}
    assert await adm.query(srequest(query, None, None, None)) == []


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
    res = await adm.query(srequest(query, geolocation, user_agent, None))
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

    res = await adm.query(srequest(query, None, None, None))
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


@pytest.mark.parametrize(
    ("query", "client_variants", "expected_is_top_pick"),
    [
        ("firefox", ["top_pick_promotion"], True),
        ("mozilla", ["top_pick_promotion"], False),
        ("firefox", [], None),
        ("firefox", ["some_other_variant"], None),
    ],
    ids=[
        "opted-in-prefix-in-query",
        "opted-in-prefix-not-in-query",
        "opted-out-no-variants",
        "opted-out-other-variant",
    ],
)
@pytest.mark.asyncio
async def test_query_is_top_pick(
    srequest: SuggestionRequestFixture,
    adm_top_pick: Provider,
    query: str,
    client_variants: list[str],
    expected_is_top_pick: bool,
) -> None:
    """`is_top_pick` is True only when the request opts into `top_pick_promotion`
    AND the record's `top_pick_prefix` is a substring of the query.
    """
    await adm_top_pick.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    res = await adm_top_pick.query(srequest(query, geolocation, user_agent, client_variants))

    assert len(res) == 1
    assert res[0].is_top_pick is expected_is_top_pick


@pytest.mark.asyncio
async def test_top_pick_promotion_metric_emitted_on_match(
    srequest: SuggestionRequestFixture,
    adm_top_pick: Provider,
) -> None:
    """The `top_pick_promotion` counter is emitted with advertiser, and
    prefix_length tags when the prefix matches the query.
    """
    await adm_top_pick.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    await adm_top_pick.query(srequest("firefox", geolocation, user_agent, ["top_pick_promotion"]))

    adm_top_pick.metrics_client.increment.assert_called_once_with(  # type: ignore[attr-defined]
        "providers.adm.top_pick_promotion",
        tags={
            "advertiser": "example.org",
            "prefix_length": 4,
        },
    )


@pytest.mark.parametrize(
    ("query", "client_variants"),
    [
        ("mozilla", ["top_pick_promotion"]),
        ("firefox", []),
        ("firefox", ["some_other_variant"]),
    ],
    ids=["opted-in-prefix-not-in-query", "opted-out-no-variants", "opted-out-other-variant"],
)
@pytest.mark.asyncio
async def test_top_pick_promotion_metric_not_emitted(
    srequest: SuggestionRequestFixture,
    adm_top_pick: Provider,
    query: str,
    client_variants: list[str],
) -> None:
    """The `top_pick_promotion` counter is not emitted when the prefix doesn't match
    or the client did not opt in.
    """
    await adm_top_pick.initialize()
    user_agent = UserAgent(form_factor="desktop", browser="firefox", os_family="macos")
    geolocation = Location(country="US")

    await adm_top_pick.query(srequest(query, geolocation, user_agent, client_variants))

    adm_top_pick.metrics_client.increment.assert_not_called()  # type: ignore[attr-defined]


SAMPLE_ENGAGEMENT_DATA = EngagementData(
    amp={
        "mozilla/firefox": KeywordEntry(
            live=KeywordMetrics(impressions=3333, clicks=88),
            historical=KeywordMetrics(impressions=6666, clicks=333),
        ),
    },
    amp_aggregated={"impressions": 463225, "clicks": 5878},
    wiki_aggregated={"impressions": 2935973, "clicks": 2325},
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


@pytest.mark.asyncio
async def test_emit_staleness_with_mars_backend(
    adm: Provider,
    backend_mock: Any,
    statsd_mock: Any,
) -> None:
    """Test that _emit_staleness emits the gauge when backend has last_new_data_at."""
    backend_mock.last_new_data_at = 1000.0

    await adm._emit_staleness()

    statsd_mock.gauge.assert_called_once()
    call_args = statsd_mock.gauge.call_args
    assert call_args[0][0] == "mars.data.staleness_seconds"
    assert call_args[1]["value"] > 0


@pytest.mark.asyncio
async def test_emit_staleness_without_mars_backend(
    adm: Provider,
    statsd_mock: Any,
) -> None:
    """Test that _emit_staleness is a no-op when backend lacks last_new_data_at."""
    await adm._emit_staleness()

    statsd_mock.gauge.assert_not_called()


@pytest.mark.asyncio
async def test_should_emit_staleness(
    adm: Provider,
    backend_mock: Any,
) -> None:
    """Test that _should_emit_staleness returns True only when backend has data."""
    assert adm._should_emit_staleness() is False

    backend_mock.last_new_data_at = 1000.0
    assert adm._should_emit_staleness() is True
