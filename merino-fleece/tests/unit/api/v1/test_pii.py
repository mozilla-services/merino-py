"""Tests for the FastAPI /api/v1/pii endpoint with a dependency-overridden detector."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from merino_fleece.app import create_app
from merino_fleece.pii import get_detector


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
    """Yield a factory that builds a TestClient with get_detector overridden."""
    apps: list[FastAPI] = []

    def _factory(verdict: bool) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_detector] = lambda: StubDetector(verdict)
        apps.append(app)
        # No `with` / lifespan needed: the dependency override skips the real
        # detector and the route does not touch app state.
        return TestClient(app)

    yield _factory

    for app in apps:
        app.dependency_overrides.clear()


def test_pii_true(make_client) -> None:
    """Detector reporting PERSON returns pii=true."""
    client = make_client(True)
    resp = client.get("/api/v1/pii", params={"q": "Barack Obama"})
    assert resp.status_code == 200
    assert resp.json() == {"pii": True}


def test_pii_false(make_client) -> None:
    """Detector reporting no PERSON returns pii=false."""
    client = make_client(False)
    resp = client.get("/api/v1/pii", params={"q": "the weather is nice"})
    assert resp.status_code == 200
    assert resp.json() == {"pii": False}


def test_missing_query(make_client) -> None:
    """A missing `q` parameter is rejected with 422."""
    client = make_client(False)
    resp = client.get("/api/v1/pii")
    assert resp.status_code == 422


def test_query_too_long(make_client) -> None:
    """A `q` exceeding the configured max length is rejected with 422."""
    client = make_client(False)
    resp = client.get("/api/v1/pii", params={"q": "x" * 501})
    assert resp.status_code == 422
