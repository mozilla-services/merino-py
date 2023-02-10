# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the
Top Picks provider.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.config import settings
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider, Suggestion
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="top_picks_data")
def fixture_top_picks_data() -> TopPicksData:
    """Define Top Picks backend suggestion content for test."""
    return TopPicksData(
        primary_index={
            "exam": [0],
            "examp": [0],
            "exampl": [0],
            "example": [0],
            "fire": [1],
            "firef": [1],
            "firefo": [1],
            "firefox": [1],
            "mozi": [2],
            "mozil": [2],
            "mozill": [2],
            "mozilla": [2],
        },
        secondary_index={
            "exxa": [0],
            "exxam": [0],
            "exxamp": [0],
            "exxampl": [0],
            "exxample": [0],
            "exam": [0],
            "examp": [0],
            "exampp": [0],
            "examppl": [0],
            "exampple": [0],
            "eexa": [0],
            "eexam": [0],
            "eexamp": [0],
            "eexampl": [0],
            "eexample": [0],
            "fire": [1, 1, 1],
            "firef": [1, 1],
            "firefo": [1, 1],
            "firefox": [1, 1],
            "firefoxx": [1],
            "foye": [1],
            "foyer": [1],
            "foyerf": [1],
            "foyerfo": [1],
            "foyerfox": [1],
            "fiir": [1],
            "fiire": [1],
            "fiiref": [1],
            "fiirefo": [1],
            "fiirefox": [1],
            "fires": [1],
            "firesf": [1],
            "firesfo": [1],
            "firesfox": [1],
            "firefoxe": [1],
            "firefoxes": [1],
            "mozz": [2],
            "mozzi": [2],
            "mozzil": [2],
            "mozzill": [2],
            "mozzilla": [2],
            "mozi": [2],
            "mozil": [2],
            "mozila": [2],
            "acbc": [3],
            "aecb": [3],
            "aecbc": [3],
        },
        short_domain_index={"ab": [3, 3], "abc": [3], "aa": [3], "ac": [3], "acb": [3]},
        results=[
            {
                "block_id": 0,
                "title": "Example",
                "url": "https://example.com",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
            },
            {
                "block_id": 0,
                "title": "Firefox",
                "url": "https://firefox.com",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
            },
            {
                "block_id": 0,
                "title": "Mozilla",
                "url": "https://mozilla.org/en-US/",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
            },
            {
                "block_id": 0,
                "title": "Abc",
                "url": "https://abc.test",
                "provider": "top_picks",
                "is_top_pick": True,
                "is_sponsored": False,
                "icon": "",
            },
        ],
        query_min=4,
        query_max=7,
        query_char_limit=4,
        firefox_char_limit=2,
    )


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture, top_picks_data: TopPicksData) -> Any:
    """Create a Top Pick backend mock object for test."""
    backend_mock: Any = mocker.AsyncMock(spec=TopPicksBackend)
    backend_mock.fetch.return_value = top_picks_data
    return backend_mock


@pytest.fixture(name="top_picks_parameters")
def fixture_top_picks_parameters() -> dict[str, Any]:
    """Define Top Pick provider parameters for test."""
    return {
        "name": "top_picks",
        "enabled_by_default": True,
        "score": settings.providers.top_picks.score,
    }


@pytest.fixture(name="providers")
def fixture_providers(
    backend_mock: Any, top_picks_parameters: dict[str, Any]
) -> Providers:
    """Define providers for this module which are injected automatically."""
    return {"top_picks": Provider(backend=backend_mock, **top_picks_parameters)}


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
