"""PII / NER detection. Owns the singleton PiiDetector and its thread pool.

The detector is initialized once at app startup via :func:`init_detector` and
served to request handlers through :func:`get_detector` (used with FastAPI
``Depends``).

SpaCy NER is CPU-bound and synchronous, so running it directly in an ``async``
handler would block the event loop and stall every concurrent request. The
shared :class:`~concurrent.futures.ThreadPoolExecutor` created by
:func:`init_executor` lets handlers offload that work off the loop. A thread
pool (rather than a process pool) keeps the single loaded model shared and
benefits from SpaCy releasing the GIL during its numeric work.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from merino_fleece.configs import settings
from merino_fleece.pii.detector import PiiDetector, build_detector

logger = logging.getLogger(__name__)

_detector: PiiDetector | None = None
_executor: ThreadPoolExecutor | None = None


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
