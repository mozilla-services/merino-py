"""Unit tests for the search term sanitization queue."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.testing.metrics import number_points
from merino_common.utils.async_batch_queue import QueueFullException
from merino_fleece.message_handlers import search_terms
from merino_fleece.sanitize import sanitizer

ParamsFactory = Callable[[str | None], SuggestRequestParams]

SANITIZE_METRIC = "search_terms.sanitize"


@pytest.fixture(name="params")
def fixture_params() -> ParamsFactory:
    """Return a factory that builds a minimal SuggestRequestParams for a given query."""

    def _build(query: str | None) -> SuggestRequestParams:
        return SuggestRequestParams(
            query=query,
            code=200,
            rid="rid",
            client_variants="",
            requested_providers="",
            browser="Firefox",
            os_family="macos",
            form_factor="desktop",
        )

    return _build


@pytest.fixture(autouse=True)
def reset_queue() -> Iterator[None]:
    """Drop the module-level queue after each test.

    The queue is a process-wide singleton and cannot be restarted once stopped, so a test
    that leaves one behind would starve every test after it.
    """
    yield
    search_terms._queue = None


@pytest.fixture
def sanitize_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[SuggestRequestParams]]:
    """Record the batches the queue's default callback hands to the sanitization pass.

    Patched at the queue module's import site, which is also what pins the default
    `on_batch` to the real pass.
    """
    calls: list[list[SuggestRequestParams]] = []

    async def _record(batch: list[SuggestRequestParams]) -> None:
        calls.append(batch)

    monkeypatch.setattr(search_terms, "sanitize_batch", _record)
    return calls


def counter_by_type(reader: InMemoryMetricReader) -> dict[str, float]:
    """Return the sanitize counter's current value per `type` attribute."""
    totals: dict[str, float] = {}
    for point in number_points(reader, SANITIZE_METRIC):
        attributes = point.attributes or {}
        pii_type = str(attributes.get("type"))
        totals[pii_type] = totals.get(pii_type, 0.0) + point.value
    return totals


def delta(before: dict[str, float], after: dict[str, float], pii_type: str) -> float:
    """Return how much the counter for `pii_type` grew between two snapshots."""
    return after.get(pii_type, 0.0) - before.get(pii_type, 0.0)


class _NeverPersonDetector:
    """Detector stub that clears every query, so NER never reclassifies a term."""

    def is_person_batch(self, texts: list[str]) -> list[bool]:
        """Return a False verdict for every text."""
        return [False] * len(texts)


@pytest.fixture
def executor() -> Iterator[ThreadPoolExecutor]:
    """Yield a single-worker pool mirroring the app's default NER pool size."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pii-detect")
    yield pool
    pool.shutdown(wait=True)


@pytest.mark.asyncio
async def test_lifecycle(
    sanitize_calls: list[list[SuggestRequestParams]], params: ParamsFactory
) -> None:
    """The queue starts, accepts terms, and stops."""
    assert search_terms.is_running() is False

    await search_terms.start()
    await search_terms.start()  # idempotent
    assert search_terms.is_running() is True

    queue = search_terms.get_queue()
    assert queue is not None
    queue.put(params("weather"))
    await search_terms.stop()

    assert search_terms.is_running() is False
    assert search_terms.get_queue() is None
    assert [term.query for batch in sanitize_calls for term in batch] == ["weather"]


@pytest.mark.asyncio
async def test_start_accepts_an_on_batch_override(params: ParamsFactory) -> None:
    """An explicit `on_batch` replaces the default sanitization pass."""
    batches: list[list[SuggestRequestParams]] = []

    async def on_batch(batch: list[SuggestRequestParams]) -> None:
        batches.append(batch)

    await search_terms.start(on_batch=on_batch)
    queue = search_terms.get_queue()
    assert queue is not None
    queue.put(params("weather"))
    await search_terms.stop()

    assert [term.query for batch in batches for term in batch] == ["weather"]


@pytest.mark.asyncio
async def test_sanitization_runs_via_the_queue(
    monkeypatch: pytest.MonkeyPatch,
    executor: ThreadPoolExecutor,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Terms put on the queue reach the real sanitization pass via the background task.

    Covers the wiring between `start`, `put`, and `sanitize_batch` that the pass's own
    tests bypass; the metric is the evidence the real pass ran.
    """
    monkeypatch.setattr(sanitizer, "get_detector", lambda: _NeverPersonDetector())
    monkeypatch.setattr(sanitizer, "get_executor", lambda: executor)
    before = counter_by_type(metric_reader)

    await search_terms.start()
    queue = search_terms.get_queue()
    assert queue is not None
    queue.put(params("the weather today"))
    queue.put(params("alice@example.com"))
    await search_terms.stop()

    after = counter_by_type(metric_reader)
    assert delta(before, after, "non_pii") == 1
    assert delta(before, after, "email") == 1


@pytest.mark.asyncio
async def test_queue_full_rejects_puts(
    monkeypatch: pytest.MonkeyPatch,
    sanitize_calls: list[list[SuggestRequestParams]],
    params: ParamsFactory,
) -> None:
    """A full queue rejects further terms rather than buffering without bound.

    A long collection delay keeps the run loop from draining the single slot before
    the second put, making the rejection deterministic. `stop()` still returns
    promptly because the collection wait races against the shutdown event.
    """
    monkeypatch.setitem(search_terms.settings.sanitize, "max_queue_size", 1)
    monkeypatch.setitem(search_terms.settings.sanitize, "max_batch_size", 1)
    monkeypatch.setitem(search_terms.settings.sanitize, "collection_delay_sec", 30.0)

    await search_terms.start()
    queue = search_terms.get_queue()
    assert queue is not None
    try:
        queue.put(params("weather"))
        assert queue.remaining_capacity() == 0
        with pytest.raises(QueueFullException):
            queue.put(params("pizza"))
    finally:
        await search_terms.stop()
