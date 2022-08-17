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


def test_request_logs_contain_required_info(mocker):
    import logging

    spy = mocker.spy(logging.Logger, "info")
    query = "nope"
    sid = "deadbeef-0000-1111-2222-333344445555"
    seq = 0
    root_path = "/api/v1/suggest"
    client.get(f"{root_path}?q={query}&sid={sid}&seq={seq}")
    extra_dict = spy.call_args[1].get("extra")
    assert extra_dict["path"] == root_path
    assert extra_dict["session_id"] == sid
    assert extra_dict["sequence_no"] == seq


# The first two IP addresses are taken from `GeoLite2-City-Test.mmdb`
@pytest.mark.parametrize(
    "ip,expected_country,expected_region,expected_city,expected_dma",
    [
        ("216.160.83.56", "US", "WA", "Milton", 819),
        ("2.125.160.216", "GB", "ENG", "Boxford", None),
        ("127.0.0.1", None, None, None, None),
    ],
)
def test_geolocation(
    mocker, ip, expected_country, expected_region, expected_city, expected_dma
):
    import logging

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = ip

    spy = mocker.spy(logging.Logger, "info")
    query = "nope"
    root_path = "/api/v1/suggest"
    client.get(f"{root_path}?q={query}")
    extra_dict = spy.call_args[1].get("extra")

    assert extra_dict["path"] == root_path
    assert extra_dict["country"] == expected_country
    assert extra_dict["region"] == expected_region
    assert extra_dict["city"] == expected_city
    assert extra_dict["dma"] == expected_dma


def test_geolocation_with_invalid_ip(mocker):
    import logging

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "invalid-ip"

    spy = mocker.spy(logging.Logger, "warning")
    client.get("/api/v1/suggest?q=nope")

    assert spy.call_count == 1
    assert spy.call_args[0][1] == "Invalid IP address for geolocation parsing"
