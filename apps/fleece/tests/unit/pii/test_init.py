"""Unit tests for the merino_fleece.pii package lifecycle helpers."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from pytest_mock import MockerFixture

import merino_fleece.pii as pii
from merino_fleece.pii import (
    get_detector,
    get_executor,
    init_detector,
    init_executor,
    shutdown_detector,
    shutdown_executor,
)


@pytest.fixture(autouse=True)
def reset_singletons() -> Iterator[None]:
    """Ensure the module-level detector/executor globals are reset around each test."""
    pii._detector = None
    pii._executor = None
    yield
    shutdown_executor()
    pii._detector = None


def test_get_detector_uninitialized_raises() -> None:
    """get_detector raises until init_detector has run."""
    with pytest.raises(RuntimeError, match="not initialized"):
        get_detector()


def test_init_and_shutdown_detector(mocker: MockerFixture) -> None:
    """init_detector builds the singleton; shutdown_detector drops it."""
    sentinel = object()
    mocker.patch("merino_fleece.pii.build_detector", return_value=sentinel)

    init_detector()
    assert get_detector() is sentinel

    shutdown_detector()
    with pytest.raises(RuntimeError, match="not initialized"):
        get_detector()


def test_get_executor_uninitialized_raises() -> None:
    """get_executor raises until init_executor has run."""
    with pytest.raises(RuntimeError, match="not initialized"):
        get_executor()


def test_init_executor_uses_configured_max_workers() -> None:
    """init_executor sizes the pool from settings.pii.executor_max_workers."""
    init_executor()
    executor = get_executor()

    assert isinstance(executor, ThreadPoolExecutor)
    assert executor._max_workers == pii.settings.pii.executor_max_workers


def test_shutdown_executor_is_idempotent() -> None:
    """shutdown_executor tolerates being called when no executor exists."""
    init_executor()
    shutdown_executor()
    shutdown_executor()  # second call is a no-op, must not raise

    with pytest.raises(RuntimeError, match="not initialized"):
        get_executor()
