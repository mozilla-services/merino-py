"""Unit tests for the Merino v1 suggest API endpoint for the Wikipedia provider."""
from unittest.mock import AsyncMock

import pytest
from elasticsearch import AsyncElasticsearch
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.wikipedia import (
    ADVERTISER,
    ICON,
    SUGGEST_ID,
    ElasticBackend,
    Provider,
    TestEchoBackend,
    WikipediaSuggestion,
)
from tests.types import FilterCaplogFixture
from tests.unit.types import SuggestionRequestFixture


@pytest.fixture(name="wikipedia")
def fixture_wikipedia() -> Provider:
    """Return an Wikipedia provider that uses a test backend."""

    return Provider(backend=TestEchoBackend())


def test_enabled_by_default(wikipedia: Provider) -> None:
    """Test for the enabled_by_default method."""

    assert wikipedia.enabled_by_default


def test_hidden(wikipedia: Provider) -> None:
    """Test for the hidden method."""

    assert not wikipedia.hidden()


@pytest.mark.asyncio
async def test_shutdown(wikipedia: Provider, mocker: MockerFixture) -> None:
    """Test for the shutdown method."""
    spy = mocker.spy(TestEchoBackend, "shutdown")
    await wikipedia.shutdown()
    spy.assert_called_once()


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
    suggestions = await wikipedia.query(srequest(query))

    assert suggestions == [
        WikipediaSuggestion(
            title=query,
            full_keyword=query,
            url=f"https://en.wikipedia.org/wiki/{expected_title}",
            advertiser=ADVERTISER,
            is_sponsored=False,
            provider="wikipedia",
            score=settings.providers.wikipedia.score,
            icon=ICON,
            block_id=0,
            impression_url=None,
            click_url=None,
        )
    ]


@pytest.mark.asyncio
async def test_es_backend_search_success(mocker: MockerFixture) -> None:
    """Test the search method of the ES backend."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "foo"}},
                            {"_source": {"title": "foo bar"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    es_backend = ElasticBackend("http://localhost:9200/")
    suggestions = await es_backend.search("foo")

    assert suggestions == [
        {
            "full_keyword": "foo",
            "title": "foo",
            "url": "https://en.wikipedia.org/wiki/foo",
        },
        {
            "full_keyword": "foo bar",
            "title": "foo bar",
            "url": "https://en.wikipedia.org/wiki/foo_bar",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_without_suggest(mocker: MockerFixture) -> None:
    """Test it can handle malformed responses (i.e. without the `suggest` field) from ES."""
    async_mock = AsyncMock(return_value={})
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    es_backend = ElasticBackend("http://localhost:9200/")
    suggestions = await es_backend.search("foo")

    assert suggestions == []


@pytest.mark.asyncio
async def test_es_backend_search_exception(
    caplog: LogCaptureFixture, filter_caplog: FilterCaplogFixture, mocker: MockerFixture
) -> None:
    """Test the exception handling in the search method of the ES backend."""
    mocker.patch.object(
        AsyncElasticsearch, "search", side_effect=Exception("404 error")
    )

    es_backend = ElasticBackend("http://localhost:9200/")
    suggestions = await es_backend.search("foo")

    records = filter_caplog(caplog.records, "merino.providers.wikipedia")

    assert suggestions == []
    assert records[0].__dict__["msg"] == "Failed to search from ES: 404 error"


@pytest.mark.asyncio
async def test_es_backend_shutdown(mocker: MockerFixture) -> None:
    """Test the shutdown method of the ES backend."""
    spy = mocker.spy(AsyncElasticsearch, "close")

    es_backend = ElasticBackend("http://localhost:9200/")
    await es_backend.shutdown()
    spy.assert_called_once()
