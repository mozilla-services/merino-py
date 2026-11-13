"""Tests for the API docs routes backed by the committed OpenAPI schema."""

import pytest
from starlette.testclient import TestClient

from merino.main import create_app
from merino.runtime import RuntimeMode
from merino.web import docs


@pytest.fixture(name="client", params=list(RuntimeMode), ids=lambda mode: mode.value)
def fixture_client(request: pytest.FixtureRequest) -> TestClient:
    """Return a client for each runtime mode, without running its lifespan or providers."""
    return TestClient(create_app(request.param))


def test_docs_is_mounted_in_every_mode(client: TestClient) -> None:
    """Every runtime mode serves the Swagger UI, pointed at /openapi.json."""
    response = client.get("/docs")

    assert response.status_code == 200
    assert "Swagger UI" in response.text
    assert "/openapi.json" in response.text


def test_openapi_serves_committed_schema_in_every_mode(client: TestClient) -> None:
    """Every runtime mode serves the committed schema, byte for byte."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.content == docs.SCHEMA_PATH.read_bytes()
