import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.integration.api.v1.util import filter_caplog
from tests.integration.api.v1.util import get_providers as override_dependency

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def inject_providers():
    app.dependency_overrides[get_providers] = override_dependency
    yield
    del app.dependency_overrides[get_providers]


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
    Despite the keyword being available for other providers, it should not return any suggestions
    if the requested provider does not exist.
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


def test_client_variants():
    response = client.get("/api/v1/suggest?q=sponsored&client_variants=foo,bar")
    assert response.status_code == 200

    result = response.json()
    assert len(result["suggestions"]) == 1
    assert result["client_variants"] == ["foo", "bar"]


def test_suggest_request_logs_contain_required_info(mocker, caplog):
    import logging

    caplog.set_level(logging.INFO)

    # Use a valid IP to avoid the geolocation errors/logs
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    query = "nope"
    sid = "deadbeef-0000-1111-2222-333344445555"
    seq = 0
    client_variants = "foo,bar"
    providers = "pro,vider"
    root_path = "/api/v1/suggest"
    client.get(
        f"{root_path}?q={query}&sid={sid}&seq={seq}"
        f"&client_variants={client_variants}&providers={providers}"
    )

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]

    assert record.name == "web.suggest.request"
    assert record.__dict__["sensitive"] is True
    assert record.__dict__["path"] == root_path
    assert record.__dict__["session_id"] == sid
    assert record.__dict__["sequence_no"] == seq
    assert record.__dict__["query"] == query
    assert record.__dict__["client_variants"] == client_variants
    assert record.__dict__["requested_providers"] == providers
    assert record.__dict__["browser"] == "Other"
    assert record.__dict__["os_family"] == "other"
    assert record.__dict__["form_factor"] == "other"


def test_non_suggest_request_logs_contain_required_info(mocker, caplog):
    import logging

    caplog.set_level(logging.INFO)

    # Use a valid IP to avoid the geolocation errors/logs
    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    client.get("/__heartbeat__")

    records = filter_caplog(caplog.records, "request.summary")

    assert len(records) == 1

    record = records[0]

    assert record.name == "request.summary"
    assert "country" not in record.__dict__["args"]
    assert "session_id" not in record.__dict__["args"]
    assert record.__dict__["path"] == "/__heartbeat__"
