# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi.testclient import TestClient

from merino.providers.top_picks import Provider as TopPicksProvider
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {"top_picks": TopPicksProvider(name="top_picks", enabled_by_default=True)}


@pytest.mark.parametrize(
    "query,title,url",
    [
        ("exam", "Example", "https://example.com"),
        ("exxa", "Example", "https://example.com"),
        ("example", "Example", "https://example.com"),
        ("firef", "Firefox", "https://firefox.com"),
        ("firefoxes", "Firefox", "https://firefox.com"),
        ("mozilla", "Mozilla", "https://mozilla.org/en-US/"),
        ("mozz", "Mozilla", "https://mozilla.org/en-US/"),
    ],
)
def test_top_picks_query(client: TestClient, query: str, title: str, url: str) -> None:
    """Test if Top Picks provider returns result for indexed Top Pick"""
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result
    assert result["suggestions"][0]["url"] == url
    assert result["suggestions"][0]["title"] == title
    assert result["suggestions"][0]["is_top_pick"]
    assert not result["suggestions"][0]["is_sponsored"]


@pytest.mark.parametrize(
    "query",
    ["m", "mo", "mox", "moz", "mozzarella", "http", "http:", "https:", "https://"],
)
def test_top_picks_no_result(client: TestClient, query: str):
    """Test if Top Picks provider does respond when provided invalid query term"""
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert result["suggestions"] == []
