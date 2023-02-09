"""Unit tests for the Merino v1 suggest API endpoint for the Wikipedia provider."""
import pytest
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.wikipedia.backends.fake_backends import FakeEchoWikipediaBackend
from merino.providers.wikipedia.provider import (
    ADVERTISER,
    ICON,
    Provider,
    WikipediaSuggestion,
)
from tests.unit.types import SuggestionRequestFixture


@pytest.fixture(name="wikipedia")
def fixture_wikipedia() -> Provider:
    """Return a Wikipedia provider that uses a test backend."""
    return Provider(
        backend=FakeEchoWikipediaBackend(),
        query_timeout_sec=0.2,
    )


def test_enabled_by_default(wikipedia: Provider) -> None:
    """Test for the enabled_by_default method."""
    assert wikipedia.enabled_by_default


def test_hidden(wikipedia: Provider) -> None:
    """Test for the hidden method."""
    assert not wikipedia.hidden()


@pytest.mark.asyncio
async def test_shutdown(wikipedia: Provider, mocker: MockerFixture) -> None:
    """Test for the shutdown method."""
    spy = mocker.spy(FakeEchoWikipediaBackend, "shutdown")
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
