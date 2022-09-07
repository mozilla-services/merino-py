import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from merino.providers.wiki_fruit import WikiFruitProvider
from tests.web.util import get_provider_factory

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def inject_providers():
    app.dependency_overrides[get_providers] = get_provider_factory({
        "wiki_fruit": WikiFruitProvider(),
    })
    yield
    del app.dependency_overrides[get_providers]


@pytest.mark.parametrize("query", ["apple", "banana", "cherry"])
def test_suggest_hit(query):
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == query
    assert result["request_id"] is not None


def test_suggest_miss():
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 0
