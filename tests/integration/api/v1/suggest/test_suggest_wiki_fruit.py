# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino v1 suggest API endpoint configured with the
Wiki Fruit provider.
"""

import pytest
from fastapi.testclient import TestClient

from merino.providers.wiki_fruit import WikiFruitProvider
from tests.integration.api.v1.types import Providers


@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    """Define providers for this module which are injected automatically."""
    return {
        "wiki_fruit": WikiFruitProvider(name="wiki_fruit", enabled_by_default=True),
    }


@pytest.mark.parametrize("query", ["apple", "banana", "cherry"])
def test_suggest_hit(client: TestClient, query: str) -> None:
    """Test that the suggest endpoint response is as expected when a suggestion is
    supplied from the wiki fruit provider.
    """
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == query
    assert result["request_id"] is not None


def test_suggest_miss(client: TestClient) -> None:
    """Test that the suggest endpoint response is as expected when a suggestion is not
    supplied from the wiki fruit provider.
    """
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 0
