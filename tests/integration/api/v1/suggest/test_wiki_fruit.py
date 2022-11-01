# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from fastapi.testclient import TestClient

from merino.providers import BaseProvider
from merino.providers.wiki_fruit import WikiFruitProvider
from tests.integration.api.v1.conftest import (
    SetupProvidersFixture,
    TeardownProvidersFixture,
)


@pytest.fixture(autouse=True)
def inject_providers(
    setup_providers: SetupProvidersFixture, teardown_providers: TeardownProvidersFixture
):
    providers: dict[str, BaseProvider] = {
        "wiki_fruit": WikiFruitProvider(name="wiki_fruit", enabled_by_default=True),
    }
    setup_providers(providers)
    yield
    teardown_providers()


@pytest.mark.parametrize("query", ["apple", "banana", "cherry"])
def test_suggest_hit(client: TestClient, query: str) -> None:
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == query
    assert result["request_id"] is not None


def test_suggest_miss(client: TestClient) -> None:
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 0
