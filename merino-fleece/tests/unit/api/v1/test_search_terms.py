"""Tests for the FastAPI /api/v1/search-terms endpoint."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from fastapi import FastAPI
from fastapi.testclient import TestClient

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.testing.metrics import counter_value
from merino_common.utils.async_batch_queue import QueueFullException
from merino_fleece.app import create_app
from merino_fleece.message_handlers.search_terms import get_message_handler

LOGGER_NAME = "merino_fleece.api.v1.search_terms"


class FakeHandler:
    """Message handler stub recording enqueued terms, with injectable failures.

    Args:
        capacity: value reported by `remaining_capacity`.
        raise_on_put: 0-based index of the put that should raise, if any. Models a
            concurrent producer consuming the headroom after the capacity check.
    """

    def __init__(self, capacity: int = 1000, raise_on_put: int | None = None) -> None:
        """Store the reported capacity and the optional failing put index."""
        self.capacity = capacity
        self.raise_on_put = raise_on_put
        self.puts: list[SuggestRequestParams] = []

    def remaining_capacity(self) -> int:
        """Return the configured capacity."""
        return self.capacity

    def put(self, message: SuggestRequestParams) -> None:
        """Record the term, or raise if this put is the configured failure point."""
        if self.raise_on_put is not None and len(self.puts) == self.raise_on_put:
            raise QueueFullException("The queue is full")
        self.puts.append(message)


# Factory yielded by `make_client`: builds a TestClient bound to a given handler.
ClientFactory = Callable[[FakeHandler], TestClient]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    """Yield a factory building a TestClient with the message handler overridden.

    No lifespan is run: the override supplies the handler, so the route never
    touches app state or the real queue.
    """
    apps: list[FastAPI] = []

    def _factory(handler: FakeHandler) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_message_handler] = lambda: handler
        apps.append(app)
        return TestClient(app)

    yield _factory

    for app in apps:
        app.dependency_overrides.clear()


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    """Yield a TestClient backed by a handler with ample capacity."""
    return make_client(FakeHandler())


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


def test_submit_search_terms(make_client: ClientFactory) -> None:
    """A valid batch returns 201, the submitted count, and reaches the queue."""
    handler = FakeHandler()
    client = make_client(handler)

    body = {"search_terms": [_search_term(query="foo"), _search_term(query="bar")]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 201
    assert resp.json() == {"submitted": 2}
    assert [term.query for term in handler.puts] == ["foo", "bar"]


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


def test_insufficient_capacity_enqueues_nothing(
    make_client: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """A submission larger than the remaining capacity is rejected atomically.

    Nothing may be enqueued: partially accepting a batch the submitter then treats
    as failed would leave the two sides disagreeing about what was processed.
    """
    handler = FakeHandler(capacity=2)
    client = make_client(handler)

    body = {"search_terms": [_search_term(query=f"q{i}") for i in range(3)]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 503
    assert handler.puts == [], "no term may be queued when the submission is rejected"
    assert any(record.name == LOGGER_NAME for record in caplog.records)


def test_handler_not_running_is_rejected(make_client: ClientFactory) -> None:
    """A handler reporting no capacity (e.g. not started) rejects submissions."""
    handler = FakeHandler(capacity=0)
    client = make_client(handler)

    resp = client.post("/api/v1/search-terms", json={"search_terms": [_search_term(query="foo")]})

    assert resp.status_code == 503
    assert handler.puts == []


def test_queue_full_midway_is_rejected(
    make_client: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """A put failing after the capacity check still returns 503.

    Concurrent submissions can both clear the capacity check and then compete for
    the same slots, so the per-put guard has to hold.
    """
    handler = FakeHandler(capacity=1000, raise_on_put=2)
    client = make_client(handler)

    body = {"search_terms": [_search_term(query=f"q{i}") for i in range(4)]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 503
    assert [term.query for term in handler.puts] == ["q0", "q1"]
    records = [record for record in caplog.records if record.name == LOGGER_NAME]
    assert records, "the partial enqueue must be logged"
    assert getattr(records[0], "accepted_count") == 2


def test_search_terms_metrics(
    make_client: ClientFactory, metric_reader: InMemoryMetricReader
) -> None:
    """The receive counter records the batch size via a real OpenTelemetry reader.

    The endpoint's counter is created against the global (proxy) meter at import
    time; the shared `metric_reader` fixture installs a MeterProvider so that proxy
    forwards to a real instrument we can read back.
    """
    before = counter_value(metric_reader, "api.search_terms.receive.count")
    client = make_client(FakeHandler())

    body = {"search_terms": [_search_term(), _search_term(), _search_term()]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 201
    assert counter_value(metric_reader, "api.search_terms.receive.count") - before == 3


def test_rejected_metric(make_client: ClientFactory, metric_reader: InMemoryMetricReader) -> None:
    """Capacity rejections are counted, since they never reach the queue's own metrics.

    The pre-check bypasses `put`, so `async_batch_queue.rejected.count` cannot see
    these; without this counter the loss would only be visible as a gap between
    received terms and queue throughput.
    """
    before = counter_value(metric_reader, "api.search_terms.reject.count")
    client = make_client(FakeHandler(capacity=0))

    body = {"search_terms": [_search_term(), _search_term()]}
    resp = client.post("/api/v1/search-terms", json=body)

    assert resp.status_code == 503
    assert counter_value(metric_reader, "api.search_terms.reject.count") - before == 2
