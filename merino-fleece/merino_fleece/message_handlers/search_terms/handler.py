"""The message handler for background search term sanitization."""

import logging
from collections import Counter
from collections.abc import Awaitable, Callable

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.utils.async_batch_queue import AsyncBatchQueue
from merino_common.utils.query_processing.pii_detect import PIIType, basic_detect
from opentelemetry import metrics

from merino_fleece.configs import settings
from merino_fleece.pii import detect_person_batch, get_detector, get_executor
from merino_fleece.utils.log_data_creator import create_search_term_log

# identifier used to tag the queue's metrics.
QUEUE_ID = "search_term_sanitization"

# Queries reaching the queue are not length-bounded by a request model the way the
# /pii endpoint's are, so they are truncated before detection.
QUERY_CHARACTER_MAX = settings.pii.query_character_max

# Whether to log `web.suggest.sanitized`.
LOG_SEARCH_TERMS: bool = settings.sanitize.log_search_terms

logger = logging.getLogger(__name__)

# web.suggest.sanitized is used for search terms that sanitization clears as NON_PII.
sanitized_term_logger = logging.getLogger("web.suggest.sanitized")

_meter = metrics.get_meter("fleece")
_sanitize_counter = _meter.create_counter(
    name="search_terms.sanitize",
    unit="{item}",
    description="Number of search terms sanitized, labeled by the detected PII type.",
)


class MessageHandler:
    """Buffers submitted search terms and sanitizes them in batches.

    Sanitization runs off the request path so submitters do not wait for it, and in
    batches so SpaCy NER can be run over many queries per model invocation.

    Args:
        on_batch: async callback for each batch. Defaults to the sanitization pass;
            override only in tests.
    """

    def __init__(
        self,
        on_batch: (Callable[[list[SuggestRequestParams]], Awaitable[object]] | None) = None,
    ) -> None:
        self._on_batch = on_batch
        self._queue: AsyncBatchQueue[SuggestRequestParams] | None = None

    async def start(self) -> None:
        """Build the queue and start its background task."""
        if self._queue is not None:
            return
        queue: AsyncBatchQueue[SuggestRequestParams] = AsyncBatchQueue(
            on_batch=self._on_batch or self.sanitize_batch,
            queue_id=QUEUE_ID,
            max_batch_size=settings.sanitize.max_batch_size,
            collection_delay_s=settings.sanitize.collection_delay_sec,
            shutdown_deadline_s=settings.sanitize.shutdown_deadline_sec,
            max_queue_size=settings.sanitize.max_queue_size,
        )
        await queue.start()
        self._queue = queue

    async def stop(self) -> None:
        """Drain the queue, then stop its background task.

        Buffered terms are sanitized before this returns, bounded by the configured
        shutdown deadline.
        """
        if self._queue is not None:
            await self._queue.stop()
            self._queue = None

    def put(self, message: SuggestRequestParams) -> None:
        """Enqueue a search term for asynchronous sanitization.

        Raises:
            RuntimeError: If the handler has not been started.
        """
        if self._queue is None:
            raise RuntimeError("The message handler is not running")
        self._queue.put(message)

    def remaining_capacity(self) -> int:
        """Return how many more search terms the queue can accept.

        Reports 0 when the handler is not running, so callers gating on capacity
        reject submissions instead of having to handle a separate not-running case.
        """
        if self._queue is None:
            return 0
        return self._queue.remaining_capacity()

    def is_running(self) -> bool:
        """Return whether the message handler's queue is running."""
        return self._queue is not None and self._queue.is_running()

    async def sanitize_batch(self, batch: list[SuggestRequestParams]) -> None:
        """Classify the PII type of every search term in the batch and record it in metrics.

        Cheap pattern matching runs over every query first; only the queries it
        clears reach SpaCy NER, which is batched via ``detect_person_batch``. The NER
        pass is chunked so the shared thread pool is released between chunks and
        concurrent `/pii` requests are not stuck behind one long batch.

        Exceptions are left to propagate: ``AsyncBatchQueue`` logs them and counts the
        batch as failed, which drops one batch rather than stopping the run loop.

        When ``sanitize.log_search_terms`` is enabled, every term the pass clears as
        ``PIIType.NON_PII`` is emitted to ``web.suggest.sanitized``. Terms of any other
        PII type are never logged, nor are terms without a query.
        """
        types: list[PIIType] = []
        # Queries still needing NER, and their positions in `types`.
        candidates: list[str] = []
        candidate_indices: list[int] = []

        for term in batch:
            query = (term.query or "")[:QUERY_CHARACTER_MAX]
            pii_type = basic_detect(query)
            if pii_type is PIIType.NON_PII and query:
                candidate_indices.append(len(types))
                candidates.append(query)
            types.append(pii_type)

        if candidates:
            detector = get_detector()
            executor = get_executor()
            chunk_size = settings.sanitize.ner_chunk_size
            for start in range(0, len(candidates), chunk_size):
                indices = candidate_indices[start : start + chunk_size]
                verdicts = await detect_person_batch(
                    candidates[start : start + chunk_size], detector, executor
                )
                # `detect_person_batch` preserves input order, so verdicts align
                # positionally with `indices`. strict=True makes any future
                # violation of that contract fail loudly rather than mislabel terms.
                for index, is_person in zip(indices, verdicts, strict=True):
                    if is_person:
                        types[index] = PIIType.PERSON

        # Aggregate before recording so a 512-term batch costs one counter add per
        # distinct PII type rather than one per term.
        for type_name, count in Counter(pii_type.name.lower() for pii_type in types).items():
            _sanitize_counter.add(count, {"type": type_name})

        # Log _only_ the sanitized search terms (i.e. those of PIIType.NON_PII)
        if LOG_SEARCH_TERMS:
            for term, pii_type in zip(batch, types, strict=True):
                if pii_type is PIIType.NON_PII and term.query:
                    log_data = create_search_term_log(term)
                    sanitized_term_logger.info("", extra=log_data.model_dump())
