"""PII / NER detection. Owns the singleton PiiDetector and its thread pool, and the
helpers that run detection on it.

The detector is initialized once at app startup via :func:`init_detector` and
served to request handlers through :func:`get_detector` (used with FastAPI
``Depends``).

SpaCy NER is CPU-bound and synchronous, so running it directly in an ``async``
handler would block the event loop and stall every concurrent request. The
shared :class:`~concurrent.futures.ThreadPoolExecutor` created by
:func:`init_executor` lets handlers offload that work off the loop. A thread
pool (rather than a process pool) keeps the single loaded model shared and
benefits from SpaCy releasing the GIL during its numeric work.

:func:`detect_person` and :func:`detect_person_batch` wrap that offload and time
it. They return plain values rather than response models, so callers that are not
HTTP handlers -- notably the background search term sanitization handler -- can use
them too.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from opentelemetry import metrics

from merino_fleece.configs import settings
from merino_fleece.pii.detector import PiiDetector, build_detector

logger = logging.getLogger(__name__)

_detector: PiiDetector | None = None
_executor: ThreadPoolExecutor | None = None

_meter = metrics.get_meter("fleece")
_ner_detect_duration = _meter.create_histogram(
    name="pii.ner_detect.duration",
    unit="ms",
    description="Duration of PII PERSON detection in milliseconds.",
)
# Batch and single-query detection get separate histograms on purpose: a batch of
# hundreds of queries and a single query are different units of work, so mixing
# them would make the single-query latency percentiles meaningless.
_ner_batch_detect_duration = _meter.create_histogram(
    name="pii.ner_batch_detect.duration",
    unit="ms",
    description="Duration of batched PII PERSON detection in milliseconds.",
)


def init_detector() -> None:
    """Build the PiiDetector singleton from settings. Call once at startup."""
    global _detector
    _detector = build_detector(settings)


def shutdown_detector() -> None:
    """Drop the PiiDetector singleton. Call once at shutdown."""
    global _detector
    _detector = None


def get_detector() -> PiiDetector:
    """Return the initialized PiiDetector. Intended for use with ``fastapi.Depends``."""
    if _detector is None:
        raise RuntimeError("PiiDetector is not initialized; init_detector() must run first")
    return _detector


def init_executor() -> None:
    """Create the shared NER thread pool from settings. Call once at startup."""
    global _executor
    _executor = ThreadPoolExecutor(
        max_workers=settings.pii.executor_max_workers,
        thread_name_prefix="pii-detect",
    )


def shutdown_executor() -> None:
    """Shut down the NER thread pool, waiting for in-flight work. Call once at shutdown."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None


def get_executor() -> ThreadPoolExecutor:
    """Return the NER thread pool. Intended for use with ``fastapi.Depends``."""
    if _executor is None:
        raise RuntimeError("PII executor is not initialized; init_executor() must run first")
    return _executor


async def detect_person(q: str, detector: PiiDetector, executor: ThreadPoolExecutor) -> bool:
    """Return whether `q` contains a PERSON named entity."""
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    try:
        return await loop.run_in_executor(executor, detector.is_person, q)
    finally:
        _ner_detect_duration.record((loop.time() - started_at) * 1000)


async def detect_person_batch(
    texts: list[str], detector: PiiDetector, executor: ThreadPoolExecutor
) -> list[bool]:
    """Return, for each text, whether it contains a PERSON named entity.

    Hands the whole batch to the detector in a single executor call, so the model's
    per-call overhead is paid once rather than once per text. Verdicts are returned
    in input order.
    """
    if not texts:
        return []
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    try:
        return await loop.run_in_executor(executor, detector.is_person_batch, texts)
    finally:
        _ner_batch_detect_duration.record((loop.time() - started_at) * 1000)
