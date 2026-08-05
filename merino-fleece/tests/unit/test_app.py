"""Tests for the merino-fleece app factory and lifespan."""

from typing import Any

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from fastapi.testclient import TestClient

from merino_common.testing.metrics import counter_value
from merino_fleece import app as app_module
from merino_fleece import pii
from merino_fleece.app import create_app
from merino_fleece.message_handlers import search_terms


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
