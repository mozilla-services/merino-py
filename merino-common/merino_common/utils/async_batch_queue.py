"""An async queue that batches items and processes them with a callback."""

import asyncio
import logging
from collections.abc import Callable, Iterable
from typing import Generic, TypeVar, Awaitable, Any
from asyncio import QueueFull
from opentelemetry.metrics import (
    CallbackOptions,
    Counter,
    MeterProvider,
    Observation,
    get_meter_provider,
)


class AsyncBatchException(Exception):
    """Base class for errors raised by AsyncBatchQueue."""

    pass


class QueueFullException(AsyncBatchException):
    """Raised by ``put`` when the queue is at capacity."""

    pass


class QueueShutDownException(AsyncBatchException):
    """Raised by ``put`` when the queue is shut down."""

    pass


T = TypeVar("T")


class AsyncBatchQueue(Generic[T]):
    """A generic class for batching and processing items asynchronously,
    one batch at a time.

    Once it is started, it will invoke ``on_batch`` callback whenever
    the maximum batch size is collected, or ``collection_delay_s`` has
    been reached (even if maximum batch size is not reached).

    To gracefully shut down, the ``stop`` method should be included in
    application lifecycle hooks. When invoked with ``force=False``, it will attempt
    to flush all remaining items in the queue (respecting ``max_batch_size``)
    without any collection delay. Once invoked, no additional items may be added
    to the queue (raises ``QueueShutDownException``). Any items remaining in the
    queue after ``shutdown_deadline_s`` will be dropped. All items not currently
    in-flight will be dropped if invoked with ``force==True``.

    Must be called from a running event loop; not thread-safe.

    Args:
        on_batch (Callable[[list[T]], Awaitable[Any]]): async callback to invoke whenever a batch
            is ready. There is no deadline on this callback, so the ``on_batch`` method itself
            should handle hung processes.
        on_error (Callable[[list[T], Exception], Awaitable[Any]], optional): async callback to invoke
            whenever ``on_batch`` raises. If not provided, errors are logged and otherwise ignored.
        max_batch_size (int, optional): The max number of items to process in a batch. Must be
            greater than 0. Defaults to 512.
        collection_delay_s (float, optional): Maximum seconds to wait for a batch to fill; a batch
            is processed as soon as it reaches ``max_batch_size`` or this delay elapses, whichever
            comes first. Defaults to 5.0.
        shutdown_deadline_s (float, optional): Seconds to wait for a graceful ``stop`` to flush the
            queue; if this deadline is exceeded, any remaining items are dropped. Defaults to 30.0.
        max_queue_size (int, optional): The max number of items to keep in the queue. Must be
            positive. Defaults to 10,000. Exceeding this value will throw QueueFullException
            when attempting to ``put`` into the queue.
        meter_provider (MeterProvider, optional): an optional opentelemetry MeterProvider;
            if unset, will pull the globally configured meter provider (or a NoOp if one
            is not configured)

    Raises:
        QueueFullException: If attempting to ``put`` onto a queue that has already reached
            ``max_queue_size``
        QueueShutDownException: If attempting to ``put`` an item after ``stop`` has been
            invoked (queue is shutting down).

    Metrics:
        Instruments are registered under the instrumentation scope
        ``merino_common.utils.async_batch_queue``:

        - ``async_batch_queue.queue.size`` (observable up-down
          counter, ``{item}``): items currently buffered, awaiting batching.
          Sampled at each export interval, so brief spikes between collections
          may be missed.
        - ``async_batch_queue.queue.capacity`` (observable gauge,
          ``{item}``): the configured ``max_queue_size``.
        - ``async_batch_queue.processed.count`` (counter,
          ``{item}``): items handed to ``on_batch``. Attributes: ``outcome``
          (``success`` or ``error``) and, on failure, ``error.type`` (the
          exception class name).
        - ``async_batch_queue.rejected.count`` (counter,
          ``{item}``): items rejected by ``put`` and never enqueued. Attribute
          ``error.type``: ``queue_full`` (at capacity) or ``shutdown`` (after
          ``stop``)

    Examples:
        ```
        batcher: AsyncBatchQueue[int] = AsyncBatchQueue(
            on_batch=batch_callback)
        await batcher.start() # begin task loop
        batcher.put(1) # will process when batch is full or wait time elapses
        # ...
        await batcher.stop() # graceful shutdown
        ```
    """

    logger = logging.getLogger(__name__)
    component_type = "async_batch_queue"

    def __init__(
        self,
        *,
        on_batch: Callable[[list[T]], Awaitable[Any]],
        on_error: Callable[[list[T], Exception], Awaitable[Any]] | None = None,
        max_batch_size: int = 512,
        collection_delay_s: float = 5.0,
        shutdown_deadline_s: float = 30.0,
        max_queue_size: int = 10000,
        meter_provider: MeterProvider | None = None,
    ):
        if max_batch_size <= 0:
            raise ValueError("Valid max_batch_size value is greater than 0")
        self.max_batch_size = max_batch_size
        self.collection_delay_s = collection_delay_s
        self.shutdown_deadline_s = shutdown_deadline_s
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=max_queue_size)
        self._current_task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._is_running = asyncio.Event()
        self._batch_callback = on_batch
        self._error_callback = on_error
        self._max_queue_size = max_queue_size
        self._processed_counter: Counter | None = None
        self._rejected_counter: Counter | None = None
        # Fall back to the globally-configured provider when none is passed. It
        # is a no-op proxy until the application sets one, so this is safe and
        # instruments start reporting automatically once a provider is set.
        self._init_metrics(meter_provider or get_meter_provider())

    def put(self, item: T) -> None:
        """Add an item to the queue for batch processing.

        Args:
            item (T): The item to process.

        Raises:
            QueueShutDownException: If the batcher has been stopped.
            QueueFullException: If the queue is at capacity and a new item
            cannot be ``put`` onto it.
        """
        if self._shutdown.is_set():
            self._record_rejected("shutdown")
            raise QueueShutDownException("The queue is shut down")
        try:
            self._queue.put_nowait(item)
        except QueueFull:
            self._record_rejected("queue_full")
            raise QueueFullException("The queue is full")
        return

    def qsize(self) -> int:
        """Return the number of items currently buffered in the queue."""
        return self._queue.qsize()

    def _collect_batch_sync(self) -> list[T]:
        """Pull up to ``max_batch_size`` items off the queue without waiting."""
        batch: list[T] = []
        while len(batch) < self.max_batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _wait_for_batch(self) -> list[T]:
        """Collect a batch, blocking for items until the delay elapses.

        Returns as soon as the batch is full, the schedule delay expires, or
        shutdown is requested. On shutdown it returns immediately rather than
        waiting out any remaining delay.
        """
        batch: list[T] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.collection_delay_s
        shutdown = asyncio.create_task(self._shutdown.wait())
        try:
            while len(batch) < self.max_batch_size:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                getter = asyncio.ensure_future(self._queue.get())
                try:
                    # Race against timeout and shutdown future
                    done, _ = await asyncio.wait(
                        {getter, shutdown},
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    if not getter.done():
                        getter.cancel()
                # Don't drop dequed items if shutdown is called
                if getter in done and not getter.cancelled():
                    batch.append(getter.result())
                else:
                    break
        finally:
            shutdown.cancel()
        return batch

    async def _flush_all(self) -> None:
        """Drain and process everything left in the queue, without delays."""
        while not self._queue.empty():
            batch = self._collect_batch_sync()
            if batch:
                await self._process(batch)

    def _init_metrics(self, meter_provider: MeterProvider) -> None:
        """Register OTel instruments for queue size, capacity, and processed count."""
        meter = meter_provider.get_meter(__name__)
        meter.create_observable_up_down_counter(
            name=f"{self.component_type}.queue.size",
            callbacks=[self._observe_queue_size],
            unit="{item}",
            description="Number of items currently buffered, waiting to be batched.",
        )
        meter.create_observable_gauge(
            name=f"{self.component_type}.queue.capacity",
            callbacks=[self._observe_queue_capacity],
            unit="{item}",
            description="Maximum number of items the queue can hold.",
        )
        self._processed_counter = meter.create_counter(
            name=f"{self.component_type}.processed.count",
            unit="{item}",
            description="Number of items handed to the batch callback, labeled by outcome.",
        )
        self._rejected_counter = meter.create_counter(
            name=f"{self.component_type}.rejected.count",
            unit="{item}",
            description="Number of items rejected by put() (never enqueued), labeled by reason.",
        )

    def _observe_queue_size(self, _options: CallbackOptions) -> Iterable[Observation]:
        """Report the current queue depth (observable up-down counter callback)."""
        yield Observation(self._queue.qsize())

    def _observe_queue_capacity(self, _options: CallbackOptions) -> Iterable[Observation]:
        """Report the queue's configured capacity (observable gauge callback)."""
        yield Observation(self._max_queue_size)

    def _record_processed(self, count: int, error: Exception | None = None) -> None:
        """Increment the processed-item counter, labeled success or error."""
        if self._processed_counter is None:
            return
        if error is not None:
            attributes = {"outcome": "error", "error.type": type(error).__name__}
        else:
            attributes = {"outcome": "success"}
        self._processed_counter.add(count, attributes)

    def _record_rejected(self, reason: str) -> None:
        """Count an item rejected by put() (never enqueued), labeled by reason."""
        if self._rejected_counter is None:
            return
        self._rejected_counter.add(1, {"error.type": reason})

    async def _process(self, batch: list[T]) -> None:
        """Run the batch callback, routing failures to the error callback."""
        try:
            await self._batch_callback(batch)
        except Exception as e:
            self.logger.error("Error processing batch", exc_info=True)
            self._record_processed(len(batch), error=e)
            if self._error_callback is not None:
                await self._error_callback(batch, e)
        else:
            self._record_processed(len(batch))

    async def start(self) -> None:
        """Start the background batch loop.

        Idempotent: repeat calls while running are a no-op. Must be called from
        within a running event loop.
        """
        if self._current_task is None:
            self._current_task = asyncio.create_task(self.run())
            # Yield once so run() reaches its first await and is_running() is
            # True by the time start() returns.
            await asyncio.sleep(0)

    async def run(self) -> None:
        """Run batch process. Collect batches until max batch size is reached,
        or configured collection wait period expires. When ready, batches are
        processed serially; this makes it safe for sinks that should not
        receive concurrent requests (e.g. an API at risk of overloading).
        While a batch is processed, the next batch is collected concurrently.

        On shutdown the loop stops collecting, finishes the in-flight request,
        and drains the remaining queue one batch at a time (with no delay in
        between collections). The overall shutdown duration is bounded by
        ``stop()`` (via ``shutdown_deadline_s``).
        """
        self._is_running.set()
        in_flight: asyncio.Task | None = None
        try:
            while not self._shutdown.is_set():
                batch = await self._wait_for_batch()
                # Ensure processing batches is done serially
                if in_flight is not None:
                    await in_flight
                    in_flight = None
                if batch:
                    in_flight = asyncio.create_task(self._process(batch))
            # On shutdown, finish the in-flight request and then drain the rest.
            if in_flight is not None:
                await in_flight
                in_flight = None
            await self._flush_all()
        finally:
            # If ``run()`` is cancelled (e.g. the shutdown deadline is exceeded),
            # make sure the in-flight request does not outlive the batcher.
            if in_flight is not None:
                in_flight.cancel()
                try:
                    await in_flight
                except asyncio.CancelledError, Exception:
                    pass
            self._is_running.clear()

    def is_running(self) -> bool:
        """Check if the batcher is running.

        Returns:
            bool: True if the batcher is running, False otherwise.
        """
        return self._is_running.is_set()

    async def stop(self, force: bool = False, timeout: float | None = None) -> None:
        """Stop the batcher asyncio task.

        Args:
            force (bool, optional): Whether to force stop the batcher without waiting for processing
                the remaining buffer items. If True, it cancels the current task and all running
                tasks and awaits their cancellation. Defaults to False.
            timeout (float, optional): Override for the graceful-shutdown deadline. If None, the
                shutdown is bounded by ``shutdown_deadline_s``. Pass a value only when you need a
                cap different from that deadline. Exceeding the deadline cancels the in-flight
                request and drain. Defaults to None.
        """
        if force:
            # Block further puts, then cancel the run loop (which cancels any
            # in-flight batch) and await the cancellation so callers know work
            # has actually stopped when stop() returns.
            self._shutdown.set()
            if self._current_task is not None and not self._current_task.done():
                self._current_task.cancel()
                await asyncio.gather(self._current_task, return_exceptions=True)
        else:
            self._shutdown.set()
            if (
                self._current_task
                and not self._current_task.done()
                and not self._current_task.get_loop().is_closed()
            ):
                # Set deadline for entire shutdown process.
                # Any items remaining in the queue after the deadline are dropped.
                deadline = timeout if timeout is not None else self.shutdown_deadline_s
                try:
                    await asyncio.wait_for(self._current_task, timeout=deadline)
                except TimeoutError:
                    self.logger.warning(
                        "Shutdown deadline exceeded; dropping remaining queue items",
                        extra={"dropped_count": self._queue.qsize()},
                    )
