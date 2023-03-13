"""Integration tests for the Wikipedia provider."""

import logging
from collections import namedtuple

import pytest
from fastapi.testclient import TestClient
from pytest import LogCaptureFixture

from merino.config import settings
from merino.providers.wikipedia.backends.fake_backends import (
    FakeEchoWikipediaBackend,
    FakeExceptionWikipediaBackend,
)
from merino.providers.wikipedia.provider import ADVERTISER, ICON, Provider
from tests.types import FilterCaplogFixture

block_list: set[str] = {"Unsafe Content", "Blocked"}

Scenario = namedtuple(
    "Scenario",
    [
        "providers",
        "query",
        "expected_suggestion_count",
        "expected_title",
        "expected_logs",
    ],
)

SCENARIOS: dict[str, Scenario] = {
    "Case-I: Backend returns": Scenario(
        providers={
            "wikipedia": Provider(
                backend=FakeEchoWikipediaBackend(), title_block_list=block_list
            )
        },
        query="foo bar",
        expected_suggestion_count=1,
        expected_title="foo_bar",
        expected_logs=set(),
    ),
    "Case-II: Backend raises": Scenario(
        providers={
            "wikipedia": Provider(
                backend=FakeExceptionWikipediaBackend(), title_block_list=block_list
            )
        },
        query="foo bar",
        expected_suggestion_count=0,
        expected_title=None,
        expected_logs={"A backend failure"},
    ),
    "Case-III: Block list filter": Scenario(
        providers={
            "wikipedia": Provider(
                backend=FakeEchoWikipediaBackend(), title_block_list=block_list
            )
        },
        query="unsafe content",
        expected_suggestion_count=0,
        expected_title=None,
        expected_logs=set(),
    ),
}


@pytest.mark.parametrize(
    argnames=[
        "providers",
        "query",
        "expected_suggestion_count",
        "expected_title",
        "expected_logs",
    ],
    argvalues=SCENARIOS.values(),
    ids=SCENARIOS.keys(),
)
def test_suggest_wikipedia(
    client: TestClient,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    query: str,
    expected_suggestion_count: int,
    expected_title,
    expected_logs: set[str],
) -> None:
    """Test for the Dynamic Wikipedia provider."""
    caplog.set_level(logging.WARNING)

    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()

    assert len(result["suggestions"]) == expected_suggestion_count

    if expected_suggestion_count > 0:
        suggestion = result["suggestions"][0]

        assert suggestion == {
            "title": query,
            "full_keyword": query,
            "url": f"https://en.wikipedia.org/wiki/{expected_title}",
            "advertiser": ADVERTISER,
            "is_sponsored": False,
            "provider": "wikipedia",
            "score": settings.providers.wikipedia.score,
            "icon": ICON,
            "block_id": 0,
            "impression_url": None,
            "click_url": None,
        }

    # Check logs for the timed out query(-ies)
    records = filter_caplog(caplog.records, "merino.providers.wikipedia.provider")

    assert {record.__dict__["msg"] for record in records} == expected_logs
