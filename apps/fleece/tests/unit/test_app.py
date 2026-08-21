"""Tests for the merino-fleece app factory and lifespan."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from fastapi.testclient import TestClient

from merino_common.testing.metrics import counter_value
from merino_fleece import app as app_module
from merino_fleece import pii
from merino_fleece.app import create_app
from merino_fleece.message_handlers import search_terms
from merino_fleece.sanitize import exempts


@pytest.fixture(autouse=True)
def _stub_global_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the lifespan's logging and Sentry setup.

    `configure_logging` applies a `dictConfig`, which replaces the process-wide
    logging configuration and so strips the handler `caplog` installs -- breaking log
    assertions in every test that runs afterwards. Both are covered by their own unit
    tests; this module is about the lifespan's resource wiring.
    """
    monkeypatch.setattr(app_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "configure_sentry", lambda **kwargs: None)


def _search_term(query: str) -> dict[str, Any]:
    """Build a valid SuggestRequestParams payload carrying `query`."""
    return {
        "query": query,
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "client_variants": "",
        "requested_providers": "",
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }


def test_lifespan_initializes_and_tears_down_dependencies(
    metric_reader: InMemoryMetricReader,
) -> None:
    """The lifespan starts the detector, thread pool, and sanitization handler, and
    tears all three down on exit.

    This also pins the shutdown ordering. A submission held by the queue's collection
    delay is only sanitized during the shutdown drain, and that drain offloads NER to
    the thread pool -- so the sanitize counter only advances if the handler drains
    *before* the pool is closed. Closing the pool first would leave the drain unable
    to schedule work, which `AsyncBatchQueue` would swallow as a failed batch.

    Loads the real SpaCy model, unlike the dependency-overridden route tests.
    """
    before = counter_value(metric_reader, "search_terms.sanitize")

    app = create_app()
    with TestClient(app) as client:
        assert search_terms.get_message_handler().is_running() is True
        assert pii.get_detector() is not None
        assert pii.get_executor() is not None

        resp = client.post(
            "/api/v1/search-terms",
            json={"search_terms": [_search_term("barack obama"), _search_term("iphone 15")]},
        )
        assert resp.status_code == 201

    assert search_terms.get_message_handler().is_running() is False
    with pytest.raises(RuntimeError):
        pii.get_detector()
    with pytest.raises(RuntimeError):
        pii.get_executor()

    assert counter_value(metric_reader, "search_terms.sanitize") - before == 2, (
        "queued terms must be sanitized during the shutdown drain"
    )


class StubExempt:
    """Exempt stub recording when it was shut down relative to the handler."""

    def __init__(self, term: str) -> None:
        """Store the term this exempt covers and init the call log."""
        self.term = term
        self.checked: list[str] = []
        self.running_at_shutdown: bool | None = None

    async def initialize(self) -> None:
        """Nothing to bootstrap; the term is fixed at construction."""

    async def shutdown(self) -> None:
        """Record whether the sanitization handler was still up when this ran."""
        self.running_at_shutdown = search_terms.get_message_handler().is_running()

    def is_exempt(self, search_term: str) -> bool:
        """Record the lookup and report whether the term is this stub's."""
        self.checked.append(search_term)
        return search_term == self.term


def test_lifespan_exempts_outlive_the_sanitization_drain(
    monkeypatch: pytest.MonkeyPatch, metric_reader: InMemoryMetricReader
) -> None:
    """Exempts are consulted by the shutdown drain and torn down only after it.

    This pins the teardown ordering. A submission held by the queue's collection delay is
    sanitized during the drain, and that pass calls `is_exempt` -- so shutting the exempts
    down before the handler drains would sanitize those terms against an empty registry.
    """
    exempt = StubExempt("firefox accounts")
    monkeypatch.setattr(exempts, "initialize", _register(exempt))
    before = counter_value(metric_reader, "search_terms.sanitize")

    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/search-terms",
            json={"search_terms": [_search_term("firefox accounts")]},
        )
        assert resp.status_code == 201

    assert exempt.checked == ["firefox accounts"], "the drain must consult the exempts"
    assert exempt.running_at_shutdown is False, "exempts must be torn down after the drain"
    assert exempts._exempts == []
    assert counter_value(metric_reader, "search_terms.sanitize") - before == 1


def _register(exempt: StubExempt) -> Callable[[], Awaitable[None]]:
    """Return a stand-in for `exempts.initialize` that registers `exempt`.

    Registering through the real `register()` keeps the teardown path under test: the
    lifespan's `shutdown()` is the thing that has to find and clear it.
    """

    async def _initialize() -> None:
        exempts.register(exempt)

    return _initialize
