import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.web.util import get_providers as override_dependency

client = TestClient(app)
app.dependency_overrides[get_providers] = override_dependency


def test_suggest_sponsored():
    response = client.get("/api/v1/suggest?q=sponsored")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "sponsored"
    assert result["request_id"] is not None


def test_suggest_nonsponsored():
    response = client.get("/api/v1/suggest?q=nonsponsored")

    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["full_keyword"] == "nonsponsored"
    assert result["request_id"] is not None


def test_no_suggestion():
    response = client.get("/api/v1/suggest?q=nope")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


@pytest.mark.parametrize("query", ["sponsored", "nonsponsored"])
def test_suggest_from_missing_providers(query):
    """
    Despite the keyword is available for other providers, it should not return any suggestions if
    the requested provider does not exist.
    """
    response = client.get(f"/api/v1/suggest?q={query}&providers=nonexist")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0


def test_no_query_string():
    response = client.get("/api/v1/suggest")
    assert response.status_code == 400


def test_providers():
    response = client.get("/api/v1/providers")
    assert response.status_code == 200

    providers = response.json()
    assert len(providers) == 2
    assert set([provider["id"] for provider in providers]) == set(
        ["sponsored-provider", "nonsponsored-provider"]
    )
