"""Tests for the FastAPI /api/v1/pii endpoint with a dependency-overridden detector."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from fastapi import FastAPI
from fastapi.testclient import TestClient

from merino_common.testing.metrics import histogram_count
from merino_fleece.app import create_app
from merino_fleece.pii import get_detector, get_executor


class StubDetector:
    """Detector stub that returns a fixed verdict."""

    def __init__(self, verdict: bool) -> None:
        """Store the verdict the stub should return."""
        self.verdict = verdict

    def is_person(self, text: str) -> bool:
        """Return the configured verdict regardless of input."""
        return self.verdict


@pytest.fixture
def make_client() -> Iterator:
    """Yield a factory that builds a TestClient with the detector and executor overridden."""
    apps: list[FastAPI] = []
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pii-detect")

    def _factory(verdict: bool) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_detector] = lambda: StubDetector(verdict)
        app.dependency_overrides[get_executor] = lambda: executor
        apps.append(app)
        # No `with` / lifespan needed: the dependency overrides supply the
        # detector and executor, so the route does not touch app state.
        return TestClient(app)

    yield _factory

    for app in apps:
        app.dependency_overrides.clear()
    executor.shutdown(wait=True)


def test_pii_true(make_client) -> None:
    """Detector reporting PERSON returns pii=true."""
    client = make_client(True)
    resp = client.post("/api/v1/pii", json={"q": "Alice Bob"})
    assert resp.status_code == 200
    assert resp.json() == {"pii": True}


def test_pii_false(make_client) -> None:
    """Detector reporting no PERSON returns pii=false."""
    client = make_client(False)
    resp = client.post("/api/v1/pii", json={"q": "the weather is nice"})
    assert resp.status_code == 200
    assert resp.json() == {"pii": False}


def test_missing_query(make_client) -> None:
    """A missing `q` field is rejected with 422."""
    client = make_client(False)
    resp = client.post("/api/v1/pii", json={})
    assert resp.status_code == 422


def test_query_too_long(make_client) -> None:
    """A `q` exceeding the configured max length is rejected with 422."""
    client = make_client(False)
    resp = client.post("/api/v1/pii", json={"q": "x" * 501})
    assert resp.status_code == 422


def test_pii_metrics(make_client, metric_reader: InMemoryMetricReader) -> None:
    """The detect-duration histogram records an observation via a real OpenTelemetry reader.

    The endpoint's histogram is created against the global (proxy) meter at import
    time; the shared `metric_reader` fixture installs a MeterProvider so that proxy
    forwards to a real instrument we can read back.
    """
    before = histogram_count(metric_reader, "pii.ner_detect.duration")

    client = make_client(True)
    resp = client.post("/api/v1/pii", json={"q": "Alice Bob"})

    assert resp.status_code == 200
    assert histogram_count(metric_reader, "pii.ner_detect.duration") - before == 1
