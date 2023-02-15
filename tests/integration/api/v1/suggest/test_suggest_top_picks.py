# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the
Top Picks provider.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient

from merino.config import settings
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider, Suggestion
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="top_picks_backend_parameters")
def fixture_top_picks_backend_parameters() -> dict[str, Any]:
    """Define Top Pick backed parameters for test."""
    return {
        "top_picks_file_path": settings.providers.top_picks.top_picks_file_path,
        "query_char_limit": settings.providers.top_picks.query_char_limit,
        "firefox_char_limit": settings.providers.top_picks.firefox_char_limit,
    }


@pytest.fixture(name="backend")
def fixture_backend(
    top_picks_backend_parameters: dict[str, Any],
) -> TopPicksBackend:
    """Create a Top Pick backend object for test."""
    backend = TopPicksBackend(**top_picks_backend_parameters)
    return backend


@pytest.fixture(name="top_picks_parameters")
def fixture_top_picks_parameters() -> dict[str, Any]:
    """Define Top Pick provider parameters for test."""
    return {
        "name": "top_picks",
        "enabled_by_default": settings.providers.top_picks.enabled_by_default,
        "score": settings.providers.top_picks.score,
    }


@pytest.fixture(name="providers")
def fixture_providers(
    backend: TopPicksBackend, top_picks_parameters: dict[str, Any]
) -> Providers:
    """Define providers for this module which are injected automatically."""
    return {"top_picks": Provider(backend=backend, **top_picks_parameters)}


@pytest.mark.parametrize("query", ["exam", "exxa", "example"])
def test_top_picks_query(client: TestClient, query: str) -> None:
    """Test if Top Picks provider returns result for indexed Top Pick"""
    expected_suggestion: list[Suggestion] = [
        Suggestion(
            block_id=0,
            title="Example",
            url="https://example.com",
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            score=settings.providers.top_picks.score,
            icon="",
        )
    ]

    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    actual_suggestions: list[Suggestion] = [
        Suggestion(**suggestion) for suggestion in result["suggestions"]
    ]
    assert actual_suggestions == expected_suggestion


@pytest.mark.parametrize(
    "query",
    ["m", "mo", "mox", "moz", "mozzarella", "http", "http:", "https:", "https://"],
)
def test_top_picks_no_result(client: TestClient, query: str):
    """Test if Top Picks provider does respond when provided invalid query term"""
    expected_suggestion: list[Suggestion] = []

    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert result["suggestions"] == expected_suggestion


@pytest.mark.parametrize(
    ["query", "title", "url"],
    [
        ("abc", "Abc", "https://abc.test"),
        ("aa", "Abc", "https://abc.test"),
        ("acb", "Abc", "https://abc.test"),
    ],
)
def test_top_picks_short_domains(
    client: TestClient, query: str, title: str, url: str
) -> None:
    """Test if Top Picks provider responds with a short domain or similar"""
    expected_suggestion: list[Suggestion] = [
        Suggestion(
            block_id=0,
            title=title,
            url=url,
            provider="top_picks",
            is_top_pick=True,
            is_sponsored=False,
            icon="",
            score=settings.providers.top_picks.score,
        )
    ]

    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert Suggestion(**result["suggestions"][0]) == expected_suggestion[0]
