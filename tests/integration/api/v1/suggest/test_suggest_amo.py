"""Integration tests for Addons"""

from collections import namedtuple
from typing import Any

import pytest
from fastapi.testclient import TestClient

from merino.providers.suggest.amo.addons_data import ADDON_KEYWORDS
from merino.providers.suggest.amo.backends.static import StaticAmoBackend
from merino.providers.suggest.amo.provider import Provider

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
        providers={"addons": Provider(backend=StaticAmoBackend(), keywords=ADDON_KEYWORDS)},
        query="night mo",
        expected_title="Dark Reader",
    ),
    "Case-II: No Addon Matches": Scenario(
        providers={"addons": Provider(backend=StaticAmoBackend(), keywords=ADDON_KEYWORDS)},
        query="nigh",
        expected_title=None,
    ),
    "Case-III: Case Insensitive Match": Scenario(
        providers={"addons": Provider(backend=StaticAmoBackend(), keywords=ADDON_KEYWORDS)},
        query="NIghT",
        expected_title="Dark Reader",
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

    # since amo provider is disabled, we shouldn't be getting any addons suggestions
    assert len(result["suggestions"]) == 0
