# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AsyncBatchQueue graceful-shutdown behavior."""

import asyncio
import os
import signal

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from merino_common.testing.metrics import collect_metrics, find_point, number_points
from merino_common.utils.async_batch_queue import (
    AsyncBatchQueue,
    QueueFullException,
    QueueShutDownException,
)

# A schedule delay long enough that no test could pass by "waiting out" the
# batching window -- a correct shutdown must actively drain, not idle.
LONG_COLLECTION_DELAY_S = 30.0


async def on_batch_noop(batch: list[int]) -> None:
    """No-op batch callback for tests that don't inspect processing."""
    pass


@pytest.mark.asyncio
async def test_sigterm_shutdown_blocks_until_queue_is_flushed() -> None:
    """Mimic a k8s pod termination: the kubelet sends SIGTERM, and graceful
    shutdown must not complete until every queued item has been flushed.

    The first batch callback is deliberately slow so a batch is still in
    flight when SIGTERM arrives. With a 30s schedule delay, the only way all
    items reach the callback within the timeout is if `stop()` finishes the
    in-flight batch and synchronously drains the remainder rather than waiting
    out the delay.
    """
    processed: list[int] = []
    errors: list[Exception] = []
    first_batch_in_flight = asyncio.Event()

    async def on_batch(batch: list[int]) -> None:
        # Hold the first batch open to guarantee in-flight work at SIGTERM time.
        if not first_batch_in_flight.is_set():
            first_batch_in_flight.set()
            await asyncio.sleep(0.1)
        processed.extend(batch)

    async def on_error(batch: list[int], exc: Exception) -> None:
        errors.append(exc)

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=3,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        meter_provider=None,
    )
    await batcher.start()

    total = 10
    for i in range(total):
        batcher.put(i)

    # Wire SIGTERM to graceful shutdown exactly as an app would for k8s.
    loop = asyncio.get_running_loop()
    shutdown_done = asyncio.Event()

    async def _graceful_terminate() -> None:
        await batcher.stop(force=False)
        shutdown_done.set()

    loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(_graceful_terminate()))
    try:
        # Let run() pick up items and get a (slow) batch in flight.
        await first_batch_in_flight.wait()

        # k8s terminates the pod.
        os.kill(os.getpid(), signal.SIGTERM)

        # Block until graceful shutdown reports completion.
        await asyncio.wait_for(shutdown_done.wait(), timeout=5.0)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        await batcher.stop(force=True)

    # Nothing was dropped and nothing errored: the full queue was flushed
    # before shutdown returned.
    assert errors == []
    assert sorted(processed) == list(range(total))
    assert not batcher._is_running.is_set()


@pytest.mark.asyncio
async def test_stop_awaits_in_flight_batch_before_returning() -> None:
    """`stop()` waits for the dispatched batch to complete processing."""
    release = asyncio.Event()
    completed: list[int] = []

    async def on_batch(batch: list[int]) -> None:
        await release.wait()  # manually block until released
        completed.extend(batch)

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=2,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        meter_provider=None,
    )
    await batcher.start()
    batcher.put(1)
    batcher.put(2)

    # Wait a short time to dispatch the batch
    await asyncio.sleep(0.01)

    stop_task = asyncio.ensure_future(batcher.stop(force=False))
    await asyncio.sleep(0.01)

    # stop() is pending because the in-flight batch hasn't completed.
    assert not stop_task.done()
    assert completed == []

    # Let the batch finish; stop() should then complete and the batch is flushed.
    release.set()
    await asyncio.wait_for(stop_task, timeout=2.0)
    assert completed == [1, 2]


@pytest.mark.asyncio
async def test_put_after_shutdown_is_rejected() -> None:
    """Once shutdown is requested, attempting to ``put`` new items raises
    QueueShutDownException
    """
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch_noop,
        max_batch_size=2,
        collection_delay_s=0.05,
        meter_provider=None,
    )
    batcher.put(1)
    await batcher.stop(force=False)

    with pytest.raises(QueueShutDownException):
        batcher.put(2)


@pytest.mark.asyncio
async def test_shutdown_deadline_drops_and_logs_and_metrics_unflushable_items(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hung callback must not hold shutdown past the deadline: the deadline
    bounds the whole graceful shutdown, drops what it can't flush, logs it,
    and emits dropped metric.
    """
    started = asyncio.Event()

    async def on_batch(batch: list[int]) -> None:
        started.set()
        await asyncio.sleep(3600)  # hang "forever"

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=1,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        shutdown_deadline_s=0.1,
        meter_provider=provider,
    )
    await batcher.start()
    for i in range(5):
        batcher.put(i)

    await started.wait()  # a batch is now hung in flight

    # Graceful stop must return within the deadline (well under the 3600s hang),
    # not block until the callback finishes.
    await asyncio.wait_for(batcher.stop(force=False), timeout=5.0)

    assert not batcher._is_running.is_set()
    assert any("Shutdown deadline exceeded" in r.message for r in caplog.records), (
        "expected a warning logging the dropped items"
    )
    dropped = number_points(reader, "async_batch_queue.dropped.count")
    assert sum(point.value for point in dropped) == 5


@pytest.mark.asyncio
async def test_force_stop_blocks_puts_and_awaits_cancellation() -> None:
    """force=True cancels in-flight work, awaits the cancellations, and refuses
    further ``put``s.
    """
    started = asyncio.Event()

    async def on_batch(batch: list[int]) -> None:
        started.set()
        await asyncio.sleep(3600)

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=1,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        meter_provider=None,
    )
    await batcher.start()
    batcher.put(1)
    await started.wait()

    await asyncio.wait_for(batcher.stop(force=True), timeout=5.0)

    assert batcher._current_task is not None and batcher._current_task.done()
    with pytest.raises(QueueShutDownException):
        batcher.put(2)


@pytest.mark.asyncio
async def test_batches_never_run_concurrently() -> None:
    """The batcher must process one batch at a time (wait for previous
    batch to finish before dispatching next)
    """
    concurrent = 0
    max_concurrent = 0
    processed_count = 0

    async def on_batch(batch: list[int]) -> None:
        nonlocal concurrent, max_concurrent, processed_count
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        # Yield so a second batch would overlap here if dispatch were parallel.
        await asyncio.sleep(0.01)
        concurrent -= 1
        processed_count += 1

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=1,  # force many batches back to back
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        meter_provider=None,
    )
    await batcher.start()
    # Enqueue enough to keep the loop dispatching batches back-to-back.
    for i in range(20):
        batcher.put(i)

    # Let it run and check shared counter
    while processed_count < 10:
        await asyncio.sleep(0.01)
    assert max_concurrent == 1, f"expected serial processing, saw {max_concurrent} concurrent"

    await batcher.stop(force=True)


@pytest.mark.asyncio
async def test_collection_overlaps_in_flight_request() -> None:
    """The next batch is collected while the current request is in flight.

    While request 1 is blocked, items enqueued for batch 2 should collected
    rather than sitting in queue until request 1 returns, ensuring throughput
    is bounded at max(delay, latency)
    """
    req1_started = asyncio.Event()
    release_req1 = asyncio.Event()
    processed: list[list[int]] = []

    async def on_batch(batch: list[int]) -> None:
        if not req1_started.is_set():
            req1_started.set()
            await release_req1.wait()  # hold request 1 open
        processed.append(batch)

    async def on_error(batch: list[int], exc: Exception) -> None:
        raise exc

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=2,
        collection_delay_s=0.02,  # short window so batch 2 collection completes fast
        meter_provider=None,
    )
    await batcher.start()
    # Batch 1 becomes the in-flight request, then blocks.
    batcher.put(1)
    batcher.put(2)
    await req1_started.wait()

    # Enqueue batch 2 while request 1 is still blocked.
    batcher.put(3)
    batcher.put(4)
    # Wait until well past the collection window; batch 2 should be collected
    await asyncio.sleep(0.1)

    assert batcher.qsize() == 0, "collection did not overlap the in-flight request"

    release_req1.set()
    await asyncio.wait_for(batcher.stop(force=False), timeout=5.0)
    assert processed == [[1, 2], [3, 4]]


@pytest.mark.asyncio
async def test_force_stop_does_not_flush_queue() -> None:
    """Force stop cancels in-flight work and does not flush.
    Only the (cancelled) in-flight batch, and remaining queue
    items are dropped.
    """
    invoked: list[list[int]] = []
    started = asyncio.Event()

    async def on_batch(batch: list[int]) -> None:
        invoked.append(list(batch))
        started.set()
        await asyncio.sleep(3600)  # hang so the batch stays in flight

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=1,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        meter_provider=None,
    )
    await batcher.start()
    for i in range(5):
        batcher.put(i)

    await started.wait()  # item 0 is in flight (hung); 1..4 still queued

    await asyncio.wait_for(batcher.stop(force=True), timeout=5.0)

    # Only the in-flight batch was ever handed out
    assert invoked == [[0]]
    # The remaining queued items were dropped
    assert batcher.qsize() > 0


@pytest.mark.asyncio
async def test_batch_seals_when_max_batch_size_reached() -> None:
    """Collection stops and fires as soon as max_batch_size is hit, without
    waiting out the (long) schedule delay.
    """
    invoked: list[list[int]] = []

    async def on_batch(batch: list[int]) -> None:
        invoked.append(list(batch))

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=3,
        collection_delay_s=LONG_COLLECTION_DELAY_S,  # would hang the test if awaited
        meter_provider=None,
    )
    await batcher.start()
    for i in range(5):
        batcher.put(i)

    # The first batch must fire on fullness alone (well before the 30s delay).
    async def first_batch() -> None:
        while not invoked:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(first_batch(), timeout=2.0)
    assert invoked[0] == [0, 1, 2]

    await batcher.stop(force=True)


@pytest.mark.asyncio
async def test_batch_processed_when_max_wait_exceeded() -> None:
    """A partial batch (fewer than max_batch_size) fires once the schedule delay
    elapses.
    """
    invoked: list[list[int]] = []

    async def on_batch(batch: list[int]) -> None:

        invoked.append(list(batch))

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=100,  # far more than we enqueue
        collection_delay_s=0.05,
        meter_provider=None,
    )
    await batcher.start()
    batcher.put(0)
    batcher.put(1)

    # Repeatedly check for a short time
    async def first_batch() -> None:
        while not invoked:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(first_batch(), timeout=5.0)
    assert invoked[0] == [0, 1]  # partial batch, sealed on the wait deadline

    await batcher.stop(force=True)


@pytest.mark.asyncio
async def test_error_callback_invoked_on_failure_batch_callback_on_success() -> None:
    """on_batch is called for every ready batch; when it raises, on_error is
    called with that batch and the exception.
    """
    calls: list[list[int]] = []
    errors: list[tuple[list[int], Exception]] = []

    async def on_batch(batch: list[int]) -> None:
        calls.append(list(batch))
        if 67 in batch:
            raise ValueError("🫲 🫴")

    async def on_error(batch: list[int], exc: Exception) -> None:
        errors.append((list(batch), exc))

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=1,  # one item per batch
        collection_delay_s=0.02,
        meter_provider=None,
    )
    await batcher.start()
    batcher.put(1)  # succeeds
    batcher.put(67)  # raises -> on_error

    # Repeatedly check for a short time
    async def both_seen() -> None:
        while len(calls) < 2 or not errors:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(both_seen(), timeout=2.0)
    await batcher.stop(force=True)

    assert calls == [[1], [67]]  # batch callback invoked for each ready batch
    assert len(errors) == 1
    failed_batch, exc = errors[0]
    assert failed_batch == [67]
    assert isinstance(exc, ValueError)


@pytest.mark.asyncio
async def test_error_callback_raise_does_not_block_batch() -> None:
    """on_batch is called for every ready batch; when it raises, on_error is
    called with that batch and the exception.
    """
    calls: list[list[int]] = []

    async def on_batch(batch: list[int]) -> None:
        calls.append(list(batch))
        if 67 in batch:
            raise ValueError("🫲 🫴")

    async def on_error(batch: list[int], exc: Exception) -> None:
        raise ValueError("🕴️")

    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=1,  # one item per batch
        collection_delay_s=0.02,
        meter_provider=None,
    )
    await batcher.start()
    batcher.put(1)  # succeeds
    batcher.put(67)  # raises -> on_error
    batcher.put(2)  # succeeds

    # Repeatedly check for a short time
    async def all_seen() -> None:
        while len(calls) < 3:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(all_seen(), timeout=2.0)
    await batcher.stop(force=True)

    # batch callback invoked after error callback raised,
    # and error callback failure batch not retried
    assert calls == [[1], [67], [2]]


@pytest.mark.asyncio
async def test_put_raises_queue_full_when_at_capacity() -> None:
    """put() past max_queue_size raises QueueFullException."""
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch_noop,
        max_batch_size=3,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        max_queue_size=3,
        meter_provider=None,
    )
    batcher.put(1)
    batcher.put(2)
    batcher.put(3)  # queue now at capacity (maxsize=3)

    # Works due to long collection delay
    with pytest.raises(QueueFullException):
        batcher.put(4)

    await batcher.stop(force=True)


@pytest.mark.asyncio
async def test_metrics_report_queue_size_capacity_and_processed() -> None:
    """A meter_provider gets queue.size, queue.capacity, and processed.count."""
    processed: list[list[int]] = []

    async def on_batch(batch: list[int]) -> None:
        processed.append(list(batch))

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=2,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        max_queue_size=100,
        meter_provider=provider,
    )
    await batcher.start()

    # Enqueue without yielding: run() hasn't executed, so all 6 are still queued.
    for i in range(6):
        batcher.put(i)
    before = collect_metrics(reader)
    assert before["async_batch_queue.queue.capacity"] == 100
    assert before["async_batch_queue.queue.size"] == 6
    assert before.get("async_batch_queue.processed.count", 0) == 0

    # Let the loop drain all six (three full batches of 2).
    async def all_processed() -> None:
        while sum(len(b) for b in processed) < 6:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(all_processed(), timeout=5.0)
    await batcher.stop(force=True)

    after = collect_metrics(reader)
    assert after["async_batch_queue.queue.size"] == 0
    assert after["async_batch_queue.processed.count"] == 6


@pytest.mark.asyncio
async def test_processed_metric_labels_failures() -> None:
    """Failed batches still count as processed, tagged with the error outcome."""

    async def on_batch(batch: list[int]) -> None:
        raise ValueError("boom")

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        max_batch_size=1,
        collection_delay_s=0.02,
        meter_provider=provider,
    )
    await batcher.start()
    batcher.put(1)

    async def one_processed() -> None:
        while collect_metrics(reader).get("async_batch_queue.processed.count", 0) < 1:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(one_processed(), timeout=5.0)
    await batcher.stop(force=True)

    # Find the processed-count data point and check its error attributes.
    points = number_points(reader, "async_batch_queue.processed.count")
    assert len(points) == 1
    assert points[0].value == 1
    attributes = points[0].attributes
    assert attributes is not None
    assert attributes["outcome"] == "error"
    assert attributes["error.type"] == "ValueError"


@pytest.mark.asyncio
async def test_rejected_metric_counts_queue_full_rejections() -> None:
    """Every put() that overflows the queue increments rejected.count with
    error.type=queue_full -- a push-based signal that never misses a drop.
    """
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch_noop,
        max_batch_size=2,
        collection_delay_s=LONG_COLLECTION_DELAY_S,
        max_queue_size=2,
        meter_provider=provider,
    )
    # Fill to capacity synchronously (run() never gets to drain), then overflow.
    batcher.put(1)
    batcher.put(2)
    for overflow in (3, 4):
        with pytest.raises(QueueFullException):
            batcher.put(overflow)

    await batcher.stop(force=True)

    points = number_points(reader, "async_batch_queue.rejected.count")
    assert len(points) == 1
    assert points[0].value == 2  # both overflowing puts counted
    attributes = points[0].attributes
    assert attributes is not None
    assert attributes["error.type"] == "queue_full"


@pytest.mark.asyncio
async def test_error_callback_metric_records_successful_error_callback() -> None:
    """When on_batch fails but on_error recovers, the on_batch failure lands on
    processed.count and the fallback success lands on error_callback.count -- so a
    healthy fallback path is a distinct metric from the failure it handled.
    """

    async def on_batch(batch: list[int]) -> None:
        raise ValueError("boom")

    async def on_error(batch: list[int], exc: Exception) -> None:
        pass  # fallback handles the batch cleanly

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=1,
        collection_delay_s=0.02,
        meter_provider=provider,
    )
    await batcher.start()
    batcher.put(1)

    # error_callback.count is recorded after processed.count, so waiting on it
    # guarantees both are present.
    async def error_callback_recorded() -> None:
        while find_point(reader, "async_batch_queue.error_callback.count") is None:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(error_callback_recorded(), timeout=5.0)
    await batcher.stop(force=True)

    processed_point = find_point(reader, "async_batch_queue.processed.count", outcome="error")
    assert processed_point is not None
    assert processed_point.value == 1
    attributes = processed_point.attributes
    assert attributes is not None
    assert attributes["error.type"] == "ValueError"

    error_point = find_point(reader, "async_batch_queue.error_callback.count", outcome="success")
    assert error_point is not None
    assert error_point.value == 1
    attributes = error_point.attributes
    assert attributes is not None
    assert "error.type" not in attributes


@pytest.mark.asyncio
async def test_error_callback_metric_records_failed_error_callback() -> None:
    """When on_error itself raises, error_callback.count records an error outcome
    tagged with the error callback's own exception type -- surfacing the silent
    data loss that occurs when both the primary and fallback paths fail.
    """

    async def on_batch(batch: list[int]) -> None:
        raise ValueError("boom")

    async def on_error(batch: list[int], exc: Exception) -> None:
        raise RuntimeError("fallback down")

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
        on_batch=on_batch,
        on_error=on_error,
        max_batch_size=1,
        collection_delay_s=0.02,
        meter_provider=provider,
    )
    await batcher.start()
    batcher.put(1)

    async def error_callback_recorded() -> None:
        while find_point(reader, "async_batch_queue.error_callback.count") is None:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(error_callback_recorded(), timeout=5.0)
    await batcher.stop(force=True)

    error_point = find_point(reader, "async_batch_queue.error_callback.count", outcome="error")
    assert error_point is not None
    assert error_point.value == 1
    attributes = error_point.attributes
    assert attributes is not None
    # error.type reflects the error callback's own exception, not on_batch's.
    assert attributes["error.type"] == "RuntimeError"
