"""Unit tests for the search term sanitization message handler."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.testing.metrics import number_points
from merino_common.utils.async_batch_queue import QueueFullException
from merino_fleece.message_handlers.search_terms import handler as handler_module
from merino_fleece.message_handlers.search_terms.handler import MessageHandler

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


@pytest.fixture
def executor() -> Iterator[ThreadPoolExecutor]:
    """Yield a single-worker pool mirroring the app's default NER pool size."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pii-detect")
    yield pool
    pool.shutdown(wait=True)


class RecordingDetector:
    """Detector stub returning preset verdicts and recording every batch it receives."""

    def __init__(self, verdicts: dict[str, bool] | None = None) -> None:
        """Store per-query verdicts (defaulting to False) and init the call log."""
        self.verdicts = verdicts or {}
        self.batch_calls: list[list[str]] = []

    def is_person_batch(self, texts: list[str]) -> list[bool]:
        """Record the batch and return each text's configured verdict."""
        self.batch_calls.append(list(texts))
        return [self.verdicts.get(text, False) for text in texts]

    @property
    def seen_queries(self) -> list[str]:
        """Every query handed to the detector, flattened across chunks."""
        return [query for call in self.batch_calls for query in call]


@pytest.fixture
def detector(monkeypatch: pytest.MonkeyPatch, executor: ThreadPoolExecutor) -> RecordingDetector:
    """Install a recording detector and the test pool as the handler's NER singletons.

    The handler looks these up per batch rather than capturing them at start, so
    patching the module's accessors is enough -- no app lifespan required.
    """
    stub = RecordingDetector()
    monkeypatch.setattr(handler_module, "get_detector", lambda: stub)
    monkeypatch.setattr(handler_module, "get_executor", lambda: executor)
    return stub


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


@pytest.mark.asyncio
async def test_lifecycle(detector: RecordingDetector, params: ParamsFactory) -> None:
    """The handler starts, accepts terms, and stops."""
    handler = MessageHandler()
    assert handler.is_running() is False

    await handler.start()
    await handler.start()  # idempotent
    assert handler.is_running() is True

    handler.put(params("weather"))
    await handler.stop()
    assert handler.is_running() is False


@pytest.mark.asyncio
async def test_put_before_start_raises(params: ParamsFactory) -> None:
    """Enqueuing before startup is a programming error, not a silent drop."""
    handler = MessageHandler()
    with pytest.raises(RuntimeError):
        handler.put(params("weather"))


def test_remaining_capacity_before_start_is_zero() -> None:
    """A handler that is not running reports no capacity rather than raising."""
    assert MessageHandler().remaining_capacity() == 0


@pytest.mark.asyncio
async def test_remaining_capacity_tracks_queue(params: ParamsFactory) -> None:
    """Once started, reported capacity reflects the terms buffered in the queue."""
    batches: list[list[SuggestRequestParams]] = []

    async def on_batch(batch: list[SuggestRequestParams]) -> None:
        batches.append(batch)

    handler = MessageHandler(on_batch=on_batch)
    await handler.start()
    try:
        capacity = handler.remaining_capacity()
        assert capacity > 0
        handler.put(params("weather"))
        assert handler.remaining_capacity() == capacity - 1
    finally:
        await handler.stop()


@pytest.mark.parametrize(
    ("query", "is_person", "expected_type", "expects_ner"),
    [
        pytest.param("alice@example.com", False, "email", False, id="email"),
        pytest.param("iphone 15 review", False, "numeric", False, id="numeric"),
        pytest.param("barack obama", True, "person", True, id="person"),
        pytest.param("the weather today", False, "non_pii", True, id="non_pii"),
        pytest.param("", False, "non_pii", False, id="empty"),
        pytest.param(None, False, "non_pii", False, id="none"),
    ],
)
@pytest.mark.asyncio
async def test_classification(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    query: str | None,
    is_person: bool,
    expected_type: str,
    expects_ner: bool,
) -> None:
    """Each search term is counted under its detected PII type.

    `expects_ner` pins the short-circuit: only queries the cheap pattern pass clears
    should reach SpaCy, since NER is by far the expensive step.
    """
    if is_person:
        detector.verdicts[str(query)] = True
    before = counter_by_type(metric_reader)

    await MessageHandler().sanitize_batch([params(query)])

    after = counter_by_type(metric_reader)
    assert delta(before, after, expected_type) == 1
    assert detector.seen_queries == ([query] if expects_ner else [])


@pytest.mark.asyncio
async def test_mixed_batch_maps_verdicts_to_the_right_terms(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Every term in a mixed batch is counted under its own type.

    Only a subset of the batch reaches NER, so verdicts are indexed against the
    filtered candidate list rather than the batch itself. This is the case that
    catches an off-by-one in that mapping: `charlie chaplin` is the only PERSON, and
    it sits after two terms that skipped NER entirely.
    """
    detector.verdicts["charlie chaplin"] = True
    batch = [
        params("the weather today"),  # non_pii, goes to NER
        params("alice@example.com"),  # email, skips NER
        params("iphone 15"),  # numeric, skips NER
        params("charlie chaplin"),  # person, goes to NER
        params(None),  # non_pii, skips NER
        params("best pizza"),  # non_pii, goes to NER
    ]
    before = counter_by_type(metric_reader)

    await MessageHandler().sanitize_batch(batch)

    after = counter_by_type(metric_reader)
    assert delta(before, after, "email") == 1
    assert delta(before, after, "numeric") == 1
    assert delta(before, after, "person") == 1
    assert delta(before, after, "non_pii") == 3
    assert detector.seen_queries == ["the weather today", "charlie chaplin", "best pizza"]


@pytest.mark.asyncio
async def test_ner_is_chunked(
    monkeypatch: pytest.MonkeyPatch,
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Candidates are split into `ner_chunk_size` calls, and verdicts still land right.

    Chunking releases the shared NER thread between calls so concurrent /pii requests
    are not stuck behind one long batch. The PERSON hit is in the final, partial chunk
    to prove the index mapping survives chunk boundaries.
    """
    monkeypatch.setitem(handler_module.settings.sanitize, "ner_chunk_size", 2)
    detector.verdicts["ada lovelace"] = True
    queries = ["one", "two", "three", "four", "ada lovelace"]
    before = counter_by_type(metric_reader)

    await MessageHandler().sanitize_batch([params(query) for query in queries])

    assert [len(call) for call in detector.batch_calls] == [2, 2, 1]
    assert detector.seen_queries == queries
    after = counter_by_type(metric_reader)
    assert delta(before, after, "person") == 1
    assert delta(before, after, "non_pii") == 4


@pytest.mark.asyncio
async def test_long_query_is_truncated(
    monkeypatch: pytest.MonkeyPatch,
    detector: RecordingDetector,
    params: ParamsFactory,
) -> None:
    """Overlong queries are truncated before detection.

    Nothing on the queue path bounds query length the way the /pii request model
    does, and one pathological query would otherwise slow its whole NER chunk.
    """
    monkeypatch.setattr(handler_module, "QUERY_CHARACTER_MAX", 5)

    await MessageHandler().sanitize_batch([params("abcdefghij")])

    assert detector.seen_queries == ["abcde"]


@pytest.mark.asyncio
async def test_empty_batch_skips_detection(detector: RecordingDetector) -> None:
    """An empty batch does no work and records nothing."""
    await MessageHandler().sanitize_batch([])
    assert detector.batch_calls == []


@pytest.mark.asyncio
async def test_sanitization_runs_via_the_queue(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Terms put on the queue are sanitized by the background task.

    Covers the wiring between `start`, `put`, and `sanitize_batch` that the direct
    `sanitize_batch` tests bypass.
    """
    detector.verdicts["barack obama"] = True
    before = counter_by_type(metric_reader)

    handler = MessageHandler()
    await handler.start()
    handler.put(params("barack obama"))
    handler.put(params("alice@example.com"))
    await handler.stop()

    after = counter_by_type(metric_reader)
    assert delta(before, after, "person") == 1
    assert delta(before, after, "email") == 1


@pytest.mark.asyncio
async def test_queue_full_rejects_puts(
    monkeypatch: pytest.MonkeyPatch, detector: RecordingDetector, params: ParamsFactory
) -> None:
    """A full queue rejects further terms rather than buffering without bound.

    A long collection delay keeps the run loop from draining the single slot before
    the second put, making the rejection deterministic. `stop()` still returns
    promptly because the collection wait races against the shutdown event.
    """
    monkeypatch.setitem(handler_module.settings.sanitize, "max_queue_size", 1)
    monkeypatch.setitem(handler_module.settings.sanitize, "max_batch_size", 1)
    monkeypatch.setitem(handler_module.settings.sanitize, "collection_delay_sec", 30.0)

    handler = MessageHandler()
    await handler.start()
    try:
        handler.put(params("weather"))
        assert handler.remaining_capacity() == 0
        with pytest.raises(QueueFullException):
            handler.put(params("pizza"))
    finally:
        await handler.stop()
