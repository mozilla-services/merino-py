"""Unit tests for the Merino v1 suggest API endpoint for the Wikipedia provider."""

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.wikipedia.backends.fake_backends import (
    FakeEchoWikipediaBackend,
)
from merino.providers.suggest.wikipedia.backends.protocol import EngagementData
from merino.providers.suggest.wikipedia.provider import (
    ADVERTISER,
    ICON,
    Provider,
    WikipediaSuggestion,
)
from merino.utils.domain_categories.models import Category
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture

SAMPLE_ENGAGEMENT_DATA = EngagementData(
    wiki_aggregated={"impressions": 2935973, "clicks": 2325},
)


@pytest.fixture(name="expected_block_list")
def fixture_expected_block_list() -> set[str]:
    """Return an expected block list."""
    return {"Unsafe Content", "Blocked"}


@pytest.fixture(name="wikipedia")
def fixture_wikipedia(expected_block_list: set[str]) -> Provider:
    """Return a Wikipedia provider that uses a test backend."""
    return Provider(
        backend=FakeEchoWikipediaBackend(),
        title_block_list=expected_block_list,
        query_timeout_sec=0.2,
        engagement_gcs_bucket="test-engagement-bucket",
        engagement_blob_name="suggest-merino-exports/engagement/keyword/latest.json",
        engagement_resync_interval_sec=3600,
        cron_interval_sec=60,
    )


def test_enabled_by_default(wikipedia: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert wikipedia.enabled_by_default is True


def test_hidden(wikipedia: Provider) -> None:
    """Test for the hidden method."""
    assert wikipedia.hidden() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("query_keyword", ["test_fail"])
async def test_query_failure(
    wikipedia: Provider, srequest: SuggestionRequestFixture, mocker, query_keyword: str
) -> None:
    """Test exception handling for the query method."""
    # Override default behavior for query
    mocker.patch.object(wikipedia, "query", side_effect=BackendError)
    with pytest.raises(BackendError):
        result = await wikipedia.query(srequest(query_keyword, None, None, None))
        assert result == []


@pytest.mark.asyncio
async def test_shutdown(wikipedia: Provider, mocker: MockerFixture) -> None:
    """Test for the shutdown method."""
    spy = mocker.spy(FakeEchoWikipediaBackend, "shutdown")
    await wikipedia.shutdown()
    spy.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Unsafe Content",
        "unsafe content",
        "Blocked",
        "blocked",
    ],
)
async def test_query_title_block_list(
    wikipedia: Provider,
    srequest: SuggestionRequestFixture,
    query: str,
) -> None:
    """Test that query method filters out blocked suggestion titles.
    Also verifies check is not case-sensitive.
    """
    suggestions = await wikipedia.query(srequest(query, None, None, None))

    assert suggestions == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ["query", "expected_title"],
    [("foo", "foo"), ("foo bar", "foo_bar"), ("foØ bÅr", "fo%C3%98_b%C3%85r")],
)
async def test_query(
    wikipedia: Provider,
    srequest: SuggestionRequestFixture,
    query: str,
    expected_title: str,
) -> None:
    """Test for the query method."""
    suggestions = await wikipedia.query(srequest(query, None, None, None))

    assert suggestions == [
        WikipediaSuggestion(
            title=query,
            full_keyword=query,
            url=HttpUrl(f"https://en.wikipedia.org/wiki/{expected_title}"),
            advertiser=ADVERTISER,
            is_sponsored=False,
            provider="wikipedia",
            score=settings.providers.wikipedia.score,
            icon=ICON,
            block_id=0,
            impression_url=None,
            click_url=None,
            categories=[Category.Education],
        )
    ]


@pytest.mark.asyncio
async def test_initialize_starts_engagement_cron(wikipedia: Provider) -> None:
    """Test that initialize() creates the engagement cron task."""
    try:
        await wikipedia.initialize()
        assert wikipedia.engagement_cron_task is not None
        assert not wikipedia.engagement_cron_task.done()
    finally:
        wikipedia.engagement_cron_task.cancel()


@pytest.mark.asyncio
async def test_fetch_engagement_data_success(
    mocker: MockerFixture,
    wikipedia: Provider,
) -> None:
    """Test that _fetch_engagement_data stores data and updates the timestamp on success."""
    mocker.patch.object(wikipedia.filemanager, "get_file", return_value=SAMPLE_ENGAGEMENT_DATA)

    assert wikipedia.last_engagement_fetch_at == 0
    await wikipedia._fetch_engagement_data()

    assert wikipedia.engagement_data == SAMPLE_ENGAGEMENT_DATA
    assert wikipedia.last_engagement_fetch_at > 0


@pytest.mark.asyncio
async def test_fetch_engagement_data_returns_none(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    wikipedia: Provider,
) -> None:
    """Test that a None return logs a warning and does not update the timestamp."""
    mocker.patch.object(wikipedia.filemanager, "get_file", return_value=None)

    await wikipedia._fetch_engagement_data()

    records = filter_caplog(caplog.records, "merino.providers.suggest.wikipedia.provider")
    assert len(records) == 1
    assert "None" in records[0].message
    assert wikipedia.engagement_data.wiki_aggregated == {}
    assert wikipedia.last_engagement_fetch_at == 0


@pytest.mark.asyncio
async def test_fetch_engagement_data_exception(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    wikipedia: Provider,
) -> None:
    """Test that an exception logs a warning and does not update the timestamp."""
    mocker.patch.object(
        wikipedia.filemanager, "get_file", side_effect=Exception("GCS unavailable")
    )

    await wikipedia._fetch_engagement_data()

    records = filter_caplog(caplog.records, "merino.providers.suggest.wikipedia.provider")
    assert len(records) == 1
    assert records[0].__dict__["error"] == "GCS unavailable"
    assert wikipedia.engagement_data.wiki_aggregated == {}
    assert wikipedia.last_engagement_fetch_at == 0
