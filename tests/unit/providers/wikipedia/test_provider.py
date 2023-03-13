"""Unit tests for the Merino v1 suggest API endpoint for the Wikipedia provider."""
import pytest
from pytest_mock import MockerFixture

from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.wikipedia.backends.fake_backends import FakeEchoWikipediaBackend
from merino.providers.wikipedia.provider import (
    ADVERTISER,
    ICON,
    Provider,
    WikipediaSuggestion,
)
from tests.unit.types import SuggestionRequestFixture


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
        result = await wikipedia.query(srequest(query_keyword))
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
    suggestions = await wikipedia.query(srequest(query))

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
