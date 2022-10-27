import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from merino.providers.top_picks import Provider as TopPicksProvider
from tests.unit.web.util import get_provider_factory

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def inject_providers():
    app.dependency_overrides[get_providers] = get_provider_factory(
        {
            "wiki_fruit": TopPicksProvider(name="top_picks", enabled_by_default=True),
        }
    )
    yield
    del app.dependency_overrides[get_providers]


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
def test_top_picks_query(query, title, url):
    """Test to determine if primary and secondary Top Picks provider results return"""
    response = client.get(f"/api/v1/suggest?q={query}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result
    assert result["suggestions"][0]["url"] == url
    assert result["suggestions"][0]["title"] == title
