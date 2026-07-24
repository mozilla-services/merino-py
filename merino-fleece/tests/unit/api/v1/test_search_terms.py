"""Tests for the FastAPI /api/v1/search-terms endpoint."""

from typing import Any

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from fastapi.testclient import TestClient

from merino_common.testing.metrics import counter_value
from merino_fleece.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Yield a TestClient for the app.

    The search-terms route has no dependencies or app state, so no lifespan
    context is needed.
    """
    return TestClient(create_app())


def _search_term(**overrides: Any) -> dict[str, Any]:
    """Build a valid SuggestRequestParams payload, applying any field overrides."""
    payload: dict[str, Any] = {
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "client_variants": "",
        "requested_providers": "",
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }
    payload.update(overrides)
    return payload


def test_submit_search_terms(client: TestClient) -> None:
    """A valid batch of search terms returns 201 and the submitted count."""
    body = {"search_terms": [_search_term(query="foo"), _search_term(query="bar")]}
    resp = client.post("/api/v1/search-terms", json=body)
    assert resp.status_code == 201
    assert resp.json() == {"submitted": 2}


def test_submit_empty_search_terms(client: TestClient) -> None:
    """An empty batch is valid and returns a submitted count of 0."""
    resp = client.post("/api/v1/search-terms", json={"search_terms": []})
    assert resp.status_code == 201
    assert resp.json() == {"submitted": 0}


def test_missing_search_terms(client: TestClient) -> None:
    """A body missing the `search_terms` field is rejected with 422."""
    resp = client.post("/api/v1/search-terms", json={})
    assert resp.status_code == 422


def test_malformed_search_term(client: TestClient) -> None:
    """A search term missing required fields is rejected with 422."""
    resp = client.post("/api/v1/search-terms", json={"search_terms": [{"query": "foo"}]})
    assert resp.status_code == 422


def test_search_terms_metrics(client: TestClient) -> None:
    """The receive counter records the batch size via a real OpenTelemetry reader.

    The endpoint's counter is created against the global (proxy) meter at import
    time; installing a MeterProvider with an InMemoryMetricReader makes that
    proxy forward to a real instrument we can read back.
    """
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))

    body = {"search_terms": [_search_term(), _search_term(), _search_term()]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 201
    assert counter_value(reader, "api.search_terms.receive.count") == 3
