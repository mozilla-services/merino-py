"""Integration tests for the Wikipedia provider."""

import pytest
from fastapi.testclient import TestClient

from merino.providers.wikipedia.backends.test_backends import TestEchoBackend
from merino.providers.wikipedia.provider import ADVERTISER, ICON, SCORE, Provider
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically.

    Note: This fixture will be overridden if a test method has a
          'pytest.mark.parametrize' decorator with a 'providers' definition
    """
    return {
        "wikipedia": Provider(backend=TestEchoBackend()),
    }


@pytest.mark.parametrize(
    ["query", "expected_title"],
    [("foo", "foo"), ("foo bar", "foo_bar"), ("foØ bÅr", "fo%C3%98_b%C3%85r")],
)
def test_suggest_wikipedia(client: TestClient, query: str, expected_title: str) -> None:
    """Test for the Dynamic Wikipedia provider."""
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()

    assert len(result["suggestions"]) == 1

    suggestion = result["suggestions"][0]

    assert suggestion == {
        "title": query,
        "full_keyword": query,
        "url": f"https://en.wikipedia.org/wiki/{expected_title}",
        "advertiser": ADVERTISER,
        "is_sponsored": False,
        "provider": "wikipedia",
        "score": SCORE,
        "icon": ICON,
        "block_id": 0,
        "impression_url": None,
        "click_url": None,
    }
