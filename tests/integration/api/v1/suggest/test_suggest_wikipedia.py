"""Integration tests for the Wikipedia provider."""

import logging
from collections import namedtuple
from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.wikipedia.backends.fake_backends import (
    FakeEchoWikipediaBackend,
    FakeExceptionWikipediaBackend,
)
from merino.providers.suggest.wikipedia.backends.protocol import WikipediaBackend
from merino.providers.suggest.wikipedia.provider import ADVERTISER, ICON, Provider
from tests.types import FilterCaplogFixture

BLOCK_LIST: set[str] = {"Unsafe Content", "Blocked"}

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
                backend=FakeEchoWikipediaBackend(),
                title_block_list=BLOCK_LIST,
                engagement_gcs_bucket="",
                engagement_blob_name="suggest-merino-exports/engagement/latest.json",
                engagement_resync_interval_sec=3600,
                cron_interval_sec=60,
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
                backend=FakeExceptionWikipediaBackend(),
                title_block_list=BLOCK_LIST,
                engagement_gcs_bucket="",
                engagement_blob_name="suggest-merino-exports/engagement/latest.json",
                engagement_resync_interval_sec=3600,
                cron_interval_sec=60,
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
                backend=FakeEchoWikipediaBackend(),
                title_block_list=BLOCK_LIST,
                engagement_gcs_bucket="",
                engagement_blob_name="suggest-merino-exports/engagement/latest.json",
                engagement_resync_interval_sec=3600,
                cron_interval_sec=60,
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
            "block_id": 0,
            "title": query,
            "full_keyword": query,
            "url": f"https://en.wikipedia.org/wiki/{expected_title}",
            "advertiser": ADVERTISER,
            "is_sponsored": False,
            "provider": "wikipedia",
            "score": settings.providers.wikipedia.score,
            "icon": ICON,
            "categories": [6],
        }

    # Check logs for the timed out query(-ies)
    records = filter_caplog(caplog.records, "merino.providers.suggest.wikipedia.provider")

    assert {record.__dict__["msg"] for record in records} == expected_logs


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a WikipediaBackend mock for circuit breaker tests,
    to allow mid-test behavior changes (from fail to recovery)
    """
    backend = mocker.AsyncMock(spec=WikipediaBackend)
    backend.shutdown = mocker.AsyncMock()
    return backend


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any) -> dict[str, Provider]:
    """Define the Wikipedia provider backed by a mock for circuit breaker tests."""
    return {
        "wikipedia": Provider(
            backend=backend_mock,
            title_block_list=set(),
            engagement_gcs_bucket="",
            engagement_blob_name="suggest-merino-exports/engagement/latest.json",
            engagement_resync_interval_sec=3600,
            cron_interval_sec=60,
        )
    }


def test_circuit_breaker_with_backend_error_wiki(
    client: TestClient,
    backend_mock: Any,
    mocker: MockerFixture,
) -> None:
    """Verify that the Wikipedia provider behaves as expected when its circuit breaker is triggered."""
    backend_mock.search.side_effect = BackendError("Elasticsearch failure")

    with freeze_time("2025-04-11") as freezer:
        # trip the breaker by hitting the failing endpoint `threshold` times
        for _ in range(settings.providers.wikipedia.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?providers=wikipedia&q=enki")

        # after open, subsequent calls should be short-circuited and not touch the backend
        spy = mocker.spy(backend_mock, "search")
        for _ in range(settings.providers.wikipedia.circuit_breaker_failure_threshold):
            _ = client.get("/api/v1/suggest?providers=wikipedia&q=enki")
        spy.assert_not_called()

        # advance time past recovery timeout to allow half-open
        freezer.tick(settings.providers.wikipedia.circuit_breaker_recover_timeout_sec + 1.0)

        # restore normal backend behavior and ensure a successful pass closes the breaker
        backend_mock.search.side_effect = None
        backend_mock.search.return_value = [
            {
                "full_keyword": "enki",
                "title": "Enki",
                "url": "https://en.wikipedia.org/wiki/Enki",
            }
        ]

        response = client.get("/api/v1/suggest?providers=wikipedia&q=enki")
        assert response.status_code == 200
        spy.assert_called_once()  # half-open allowed a trial call through

        # subsequent requests should also succeed (breaker back to closed)
        for _ in range(settings.providers.wikipedia.circuit_breaker_failure_threshold):
            response = client.get("/api/v1/suggest?providers=wikipedia&q=enki")
            assert response.status_code == 200
