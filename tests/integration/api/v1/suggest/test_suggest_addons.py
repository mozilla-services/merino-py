"""Integration tests for Addons"""
from collections import namedtuple
from typing import Any

import pytest
from fastapi.testclient import TestClient

from merino.providers.addons.addons_data import KEYWORDS
from merino.providers.addons.backends.static import StaticAddonsBackend
from merino.providers.addons.provider import Provider

Scenario = namedtuple(
    "Scenario",
    [
        "providers",
        "query",
        "expected_title",
    ],
)

SCENARIOS: dict[str, Scenario] = {
    "Case-I: Returns Matched Addon": Scenario(
        providers={
            "addons": Provider(backend=StaticAddonsBackend(), keywords=KEYWORDS)
        },
        query="nigh",
        expected_title="Dark Reader",
    ),
    "Case-II: No Addon Matches": Scenario(
        providers={
            "addons": Provider(backend=StaticAddonsBackend(), keywords=KEYWORDS)
        },
        query="asdf",
        expected_title=None,
    ),
}


@pytest.mark.parametrize(
    argnames=["providers", "query", "expected_title"],
    argvalues=SCENARIOS.values(),
    ids=SCENARIOS.keys(),
)
def test_suggest_addons(client: TestClient, query: str, expected_title: dict[str, Any]):
    """Integration tests for Addons Suggestions."""
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()

    if expected_title:
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["title"] == expected_title
    else:
        assert len(result["suggestions"]) == 0