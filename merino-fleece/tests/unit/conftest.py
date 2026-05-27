"""Shared test configuration for merino-fleece. Must set MERINO_FLEECE_ENV before any merino_fleece import."""

import logging
import os

import pytest

os.environ.setdefault("MERINO_FLEECE_ENV", "testing")


@pytest.fixture(autouse=True)
def _propagate_merino_fleece_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the `merino_fleece` logger to propagate so pytest's `caplog` can capture records.

    Other tests in the session (notably the `configure_logging` unit tests) call
    `configure_logging(..., can_propagate=False)` against the `merino_fleece` logger, which
    persists in the global `logging` state and silently blocks records from reaching the root
    logger where `caplog` listens. Restoring propagation per-test keeps log assertions robust
    regardless of test ordering.
    """
    monkeypatch.setattr(logging.getLogger("merino_fleece"), "propagate", True)
