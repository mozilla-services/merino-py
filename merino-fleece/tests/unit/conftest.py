"""Shared test configuration for merino-fleece. Must set MERINO_FLEECE_ENV before any merino_fleece import."""

import logging
import os

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

os.environ.setdefault("MERINO_FLEECE_ENV", "testing")


@pytest.fixture(scope="session")
def metric_reader() -> InMemoryMetricReader:
    """Install a process-global MeterProvider once and expose its reader.

    OpenTelemetry only honors the first `set_meter_provider()` call per process, so
    the provider must be configured a single time and shared across tests. The proxy
    instruments created at import time rebind to this provider on the first set, so
    reading the same reader works regardless of test ordering. Metrics accumulate
    across the session; assert on deltas rather than absolute values.
    """
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    return reader


@pytest.fixture(autouse=True)
def _propagate_merino_fleece_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the merino-fleece loggers to propagate so pytest's `caplog` can capture records.

    Other tests in the session (notably the `configure_logging` unit tests) call
    `configure_logging(..., can_propagate=False)`, which turns propagation off for every logger
    it configures. That persists in the global `logging` state and silently blocks records from
    reaching the root logger where `caplog` listens. Restoring propagation per-test keeps log
    assertions robust regardless of test ordering. `web.suggest.sanitized` is configured by name
    rather than as a child of `merino_fleece`, so it needs restoring separately.
    """
    for name in ("merino_fleece", "web.suggest.sanitized"):
        monkeypatch.setattr(logging.getLogger(name), "propagate", True)
