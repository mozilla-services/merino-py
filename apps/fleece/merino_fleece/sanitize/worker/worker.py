"""Pub/Sub worker for processing search term submissions.

Consumes the backup channel merino falls back to when direct submission to merino-fleece
fails, and runs each message's search terms through the same sanitization pass the HTTP
endpoint uses.

The client is `gcloud-aio-pubsub`, whose subscriber is native asyncio: its handler is a
coroutine, so `sanitize_batch` is simply awaited on the loop that already owns the SpaCy
detector and the exempts registry. `subscribe()` acks a message only after its handler
returns and nacks it if the handler raises, which is exactly the delivery contract this
worker wants.
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from gcloud.aio.pubsub import SubscriberMessage
from merino_common.models.suggest_logging import SearchTermsSubmission
from pydantic import ValidationError

from merino_fleece.sanitize.sanitizer import sanitize_batch

logger = logging.getLogger(__name__)

MessageHandler = Callable[[SubscriberMessage], Awaitable[None]]


# Pub/Sub caps a single pull request at 1000 messages.
MAX_PULL_LIMIT = 1000

# A pessimistic ceiling on how long sanitizing one message takes. Measured: a full
# 512-term batch runs ~161ms on `en_core_web_sm`, leaving roughly 6x headroom for the
# larger `en_core_web_lg` that deployed environments load.
SLOW_BATCH_S = 1.0

# Messages handled concurrently per NER thread. At 2, one batch per thread is in NER while
# another is ready to take its place, so a thread never waits on a pull. Higher values only
# deepen the queue, and queued messages are already burning their ack deadline.
MESSAGES_PER_NER_WORKER = 2


@dataclass(frozen=True)
class SubscriberTuning:
    """Subscriber limits derived from the subscription's ack deadline and the NER pool.

    The ack deadline is a hard budget rather than a target: `gcloud-aio-pubsub` never
    extends leases, so a message not acked within it is redelivered while still being
    handled, and its terms are sanitized -- and logged -- twice. The deadline is therefore
    split in thirds: one absorbs time spent waiting in the local queue, one is the ceiling
    on sanitizing a single message, and the last is left unused as margin.

    Deriving these rather than configuring them keeps that budget internally consistent:
    the two inputs are facts about the deployment (what terraform set on the subscription,
    how many cores the pod has), and everything else follows.

    Only `num_producers=1` upholds this. The library gives each producer its own queue and
    consumer, so a second producer would double both concurrency and queue depth.

    Example:
        The deployed default -- a 30s deadline and a single NER thread::

            >>> SubscriberTuning.derive(ack_deadline_s=30.0, ner_workers=1)
            SubscriberTuning(concurrency=2, max_messages_per_pull=20, sanitize_timeout_s=10.0)

        Two messages sanitize at a time, at most 20 wait locally, and any single one is
        abandoned after 10s. Worst case, a message waits (20 / 2) * 1.0 = 10s to start and
        10s to run, so it acks by 20s -- a full 10s inside the deadline.

        Scaling the pod to 4 NER threads scales concurrency and prefetch together, while
        the per-message ceiling belongs to the deadline and does not move::

            >>> SubscriberTuning.derive(ack_deadline_s=30.0, ner_workers=4)
            SubscriberTuning(concurrency=8, max_messages_per_pull=80, sanitize_timeout_s=10.0)

        Worst-case queue wait is still (80 / 8) * 1.0 = 10s: prefetch and concurrency
        scale in step, so the budget holds at any pod size.
    """

    concurrency: int
    max_messages_per_pull: int
    sanitize_timeout_s: float

    @classmethod
    def derive(cls, ack_deadline_s: float, ner_workers: int) -> "SubscriberTuning":
        """Split `ack_deadline_s` into thirds and size the subscriber against it.

        Args:
            ack_deadline_s: The subscription's configured ack deadline, in seconds.
            ner_workers: Size of this process's NER thread pool
                (`pii.executor_max_workers`), which is what bounds useful concurrency.
        """
        concurrency = ner_workers * MESSAGES_PER_NER_WORKER
        third = ack_deadline_s / 3
        # Never prefetch less than can be worked on at once, nor more than Pub/Sub allows.
        prefetch = min(MAX_PULL_LIMIT, max(concurrency, int(concurrency * third / SLOW_BATCH_S)))
        return cls(
            concurrency=concurrency,
            max_messages_per_pull=prefetch,
            sanitize_timeout_s=third,
        )


def build_handler(sanitize_timeout_s: float) -> MessageHandler:
    """Build the per-message handler `subscribe()` invokes.

    The handler's outcome decides the message's fate, per `subscribe()`'s contract:
    returning acks it, raising nacks it. So:

    - Sanitized successfully: returns, and the message is acked. The ack therefore means
      the terms have been classified and logged, not merely received.
    - Unparseable: logged and acked. A message that does not parse never will, so nacking
      it would redeliver it forever.
    - Sanitization failed or overran `sanitize_timeout_s`: the exception propagates and
      the message is nacked for redelivery.

    The timeout lives inside the handler so cancellation is native: `asyncio.timeout`
    cancels the pass in place, and because every `await` in that pass precedes its metrics
    and data-log writes, a cancelled batch emits nothing partial.

    `sanitize_timeout_s` must stay well inside the subscription's ack deadline. The client
    does not extend leases while a handler runs, so a handler that outlives the deadline
    has its message redelivered underneath it and the same terms are logged twice. See the
    budget documented over `[default.pubsub]`.
    """

    async def handler(message: SubscriberMessage) -> None:
        try:
            submission = SearchTermsSubmission.model_validate_json(message.data or b"")
        except ValidationError:
            logger.exception("Dropping invalid message")
            return

        try:
            async with asyncio.timeout(sanitize_timeout_s):
                await sanitize_batch(submission.search_terms)
        except TimeoutError:
            logger.error(
                "Timed out sanitizing search terms; message will be redelivered",
                extra={
                    "term_count": len(submission.search_terms),
                    "timeout_s": sanitize_timeout_s,
                },
            )
            raise

    return handler


async def heartbeat(path: str, interval: float) -> None:
    """Refresh `path` every `interval` seconds, for an external liveness probe.

    Runs as a task on the same loop as message handling, which is what makes it a useful
    signal: if the loop stalls, the file goes stale and the probe restarts the pod. Parent
    directories are created on demand.

    Write failures are logged and retried on the next tick rather than killing the task. A
    transient failure (e.g. a full disk) recovers; a persistent one (e.g. a permissions
    error) leaves the file stale, so the probe restarts the pod.
    """
    while True:
        try:
            await asyncio.to_thread(_write_heartbeat, path)
        except OSError:
            logger.exception("Failed to refresh heartbeat file", extra={"path": path})
        await asyncio.sleep(interval)


def _write_heartbeat(path: str) -> None:
    """Atomically write the current epoch seconds to the heartbeat file."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        fh.write(str(int(time.time())))
    os.replace(tmp, path)  # atomic rename; the probe never sees a partial write
