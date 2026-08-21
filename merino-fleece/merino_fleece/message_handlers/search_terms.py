"""The queue that buffers submitted search terms for background sanitization.

Sanitization runs off the request path so submitters do not wait for it, and in batches so
SpaCy NER can be run over many queries per model invocation. What a batch actually does
lives in :mod:`merino_fleece.sanitize.sanitizer`, which this module shares with the Pub/Sub
backup-channel worker.

The queue is a process-wide singleton because its OpenTelemetry instruments are registered
for the life of the meter provider, so short-lived instances would pin them in memory and
emit duplicate-instrument warnings.
"""

from collections.abc import Awaitable, Callable

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.utils.async_batch_queue import AsyncBatchQueue

from merino_fleece.configs import settings
from merino_fleece.sanitize.sanitizer import sanitize_batch

__all__ = ["QUEUE_ID", "start", "stop", "get_queue", "is_running"]

# identifier used to tag the queue's metrics.
QUEUE_ID = "search_term_sanitization"

BatchCallback = Callable[[list[SuggestRequestParams]], Awaitable[object]]

# Built by `start()` rather than here: an `AsyncBatchQueue` cannot be restarted once
# stopped, and it must be constructed under the loop that will drive it.
_queue: AsyncBatchQueue[SuggestRequestParams] | None = None


async def start(on_batch: BatchCallback | None = None) -> None:
    """Build the queue and start its background task. Call once at startup.

    Args:
        on_batch: async callback for each batch. Defaults to the sanitization pass;
            override only in tests.
    """
    global _queue
    if _queue is not None:
        return
    queue: AsyncBatchQueue[SuggestRequestParams] = AsyncBatchQueue(
        on_batch=on_batch or sanitize_batch,
        queue_id=QUEUE_ID,
        max_batch_size=settings.sanitize.max_batch_size,
        collection_delay_s=settings.sanitize.collection_delay_sec,
        shutdown_deadline_s=settings.sanitize.shutdown_deadline_sec,
        max_queue_size=settings.sanitize.max_queue_size,
    )
    await queue.start()
    _queue = queue


async def stop() -> None:
    """Drain the queue, then stop its background task. Call once at shutdown.

    Buffered terms are sanitized before this returns, bounded by the configured
    shutdown deadline.
    """
    global _queue
    if _queue is not None:
        await _queue.stop()
        _queue = None


def get_queue() -> AsyncBatchQueue[SuggestRequestParams] | None:
    """Return the queue, or None when it is not running.

    Intended for use with ``fastapi.Depends``. Returns None rather than raising so callers
    can report the queue as unavailable instead of failing the request outright.
    """
    return _queue


def is_running() -> bool:
    """Return whether the queue is running."""
    return _queue is not None and _queue.is_running()
