"""Unit tests for the merino_fleece.pii package detection helpers.

The detector is stubbed so these tests cover the offload-and-measure wrapper
rather than SpaCy's behavior, which `test_detector.py` covers against the real
model.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from merino_common.testing.metrics import histogram_count
from merino_fleece.pii import detect_person, detect_person_batch
from merino_fleece.pii.detector import PiiDetector


class StubDetector:
    """Detector stub that records its calls and returns preset verdicts."""

    def __init__(self, verdicts: list[bool] | None = None) -> None:
        """Store the verdicts to return and initialize the call log."""
        self.verdicts = verdicts if verdicts is not None else []
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def is_person(self, text: str) -> bool:
        """Record the call and return the first configured verdict."""
        self.single_calls.append(text)
        return self.verdicts[0]

    def is_person_batch(self, texts: list[str]) -> list[bool]:
        """Record the call and return the configured verdicts."""
        self.batch_calls.append(list(texts))
        return self.verdicts[: len(texts)]


def as_detector(stub: StubDetector) -> PiiDetector:
    """Present the stub as a PiiDetector for the service's type signature."""
    return cast(PiiDetector, stub)


@pytest.fixture
def executor() -> Iterator[ThreadPoolExecutor]:
    """Yield a single-worker pool mirroring the app's default NER pool size."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pii-detect")
    yield pool
    pool.shutdown(wait=True)


@pytest.mark.asyncio
async def test_detect_person_returns_verdict(executor: ThreadPoolExecutor) -> None:
    """The detector's verdict is returned and the query reaches it unchanged."""
    stub = StubDetector([True])

    assert await detect_person("Alice Bob", as_detector(stub), executor) is True
    assert stub.single_calls == ["Alice Bob"]


@pytest.mark.asyncio
async def test_detect_person_records_duration(
    executor: ThreadPoolExecutor, metric_reader: InMemoryMetricReader
) -> None:
    """Single-query detection records one observation on the endpoint histogram."""
    before = histogram_count(metric_reader, "pii.ner_detect.duration")

    await detect_person("Alice Bob", as_detector(StubDetector([False])), executor)

    assert histogram_count(metric_reader, "pii.ner_detect.duration") - before == 1


@pytest.mark.asyncio
async def test_detect_person_batch_returns_verdicts_in_order(
    executor: ThreadPoolExecutor,
) -> None:
    """Verdicts come back positionally aligned with the submitted texts."""
    stub = StubDetector([False, True, False])

    verdicts = await detect_person_batch(
        ["weather", "Alice Bob", "pizza"], as_detector(stub), executor
    )

    assert verdicts == [False, True, False]


@pytest.mark.asyncio
async def test_detect_person_batch_uses_a_single_detector_call(
    executor: ThreadPoolExecutor,
) -> None:
    """The whole batch is handed to the detector at once.

    Batching exists to pay the model's per-call overhead once instead of once per
    text, so a regression to per-text calls must fail here.
    """
    stub = StubDetector([False, False, False, False])
    texts = ["a", "b", "c", "d"]

    await detect_person_batch(texts, as_detector(stub), executor)

    assert stub.batch_calls == [texts], "expected exactly one batched call"
    assert stub.single_calls == [], "per-text detection defeats the point of batching"


@pytest.mark.asyncio
async def test_detect_person_batch_records_its_own_duration(
    executor: ThreadPoolExecutor, metric_reader: InMemoryMetricReader
) -> None:
    """Batch detection records one observation, on its own histogram.

    The batch histogram is separate from `pii.ner_detect.duration` so batch timings
    cannot distort the single-query latency distribution.
    """
    single_before = histogram_count(metric_reader, "pii.ner_detect.duration")
    batch_before = histogram_count(metric_reader, "pii.ner_batch_detect.duration")

    await detect_person_batch(["a", "b", "c"], as_detector(StubDetector([False] * 3)), executor)

    assert histogram_count(metric_reader, "pii.ner_batch_detect.duration") - batch_before == 1
    assert histogram_count(metric_reader, "pii.ner_detect.duration") == single_before


@pytest.mark.asyncio
async def test_detect_person_batch_empty(
    executor: ThreadPoolExecutor, metric_reader: InMemoryMetricReader
) -> None:
    """An empty batch short-circuits without touching the detector or the histogram."""
    stub = StubDetector()
    before = histogram_count(metric_reader, "pii.ner_batch_detect.duration")

    assert await detect_person_batch([], as_detector(stub), executor) == []

    assert stub.batch_calls == []
    assert histogram_count(metric_reader, "pii.ner_batch_detect.duration") == before
